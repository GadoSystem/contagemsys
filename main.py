from __future__ import annotations

import argparse
import os
import threading
import time
from pathlib import Path
from typing import Any

import cv2
import uvicorn
from dotenv import load_dotenv
from ultralytics import YOLO

from api import create_app
from auth import AuthService
from camera_stream import LatestFrameCamera
from config import load_config, resolve_project_path, resolve_tracker
from counting import GateCounter
from evidence import EvidenceRecorder
from persistence import EventDatabase
from state import LiveFrameStore, SharedState

BASE_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sistema de contagem direcional V5 - multi-camera web")
    parser.add_argument("--config", default=str(BASE_DIR / "config.yaml"))
    return parser.parse_args()


def roi_crop(frame, roi_cfg: dict):
    h, w = frame.shape[:2]
    if not roi_cfg.get("enabled", False):
        return frame, (0, 0, w, h)
    x1 = int(w * float(roi_cfg["x1"]))
    y1 = int(h * float(roi_cfg["y1"]))
    x2 = int(w * float(roi_cfg["x2"]))
    y2 = int(h * float(roi_cfg["y2"]))
    return frame[y1:y2, x1:x2], (x1, y1, x2, y2)


def draw_gate(frame, roi_box: tuple[int, int, int, int], gate_cfg: dict) -> None:
    x1, y1, x2, y2 = roi_box
    width = x2 - x1
    left = x1 + int(width * float(gate_cfg["left_x"]))
    right = x1 + int(width * float(gate_cfg["right_x"]))
    cv2.rectangle(frame, (x1, y1), (x2 - 1, y2 - 1), (120, 120, 120), 1)
    cv2.line(frame, (left, y1), (left, y2), (0, 200, 255), 2)
    cv2.line(frame, (right, y1), (right, y2), (0, 200, 255), 2)
    cv2.putText(frame, "LEFT", (x1 + 8, y1 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
    cv2.putText(frame, "GATE", (left + 8, y1 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
    cv2.putText(frame, "RIGHT", (right + 8, y1 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)


def draw_hud(frame, snap: dict) -> None:
    lines = [
        f"CAMERA: {snap['camera_name']}",
        f"CONTADOS: {snap['total_contado']}",
        f"NO FRAME: {snap['animais_no_frame_agora']}",
        f"RETORNOS: {snap['retornos_esquerda_para_direita']}",
        f"FPS camera: {snap['fps_camera']:.1f}",
        f"FPS IA: {snap['fps_ia']:.1f}",
        f"latencia IA: {snap['latencia_ia_ms']:.1f} ms",
        f"session: {snap['session_id']}",
    ]
    y = 30
    for text in lines:
        cv2.putText(frame, text, (14, y), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (30, 255, 30), 2)
        y += 26


def compose_display(frame, snap: dict, display_cfg: dict):
    sidebar = display_cfg.get("sidebar", {})
    if not sidebar.get("enabled", True):
        draw_hud(frame, snap)
        return frame

    width = max(230, int(sidebar.get("width", 280)))
    position = str(sidebar.get("position", "left")).lower()

    if position == "right":
        canvas = cv2.copyMakeBorder(frame, 0, 0, 0, width, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        panel_x = frame.shape[1]
    else:
        canvas = cv2.copyMakeBorder(frame, 0, 0, width, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        panel_x = 0

    x = panel_x + 16
    panel_right = panel_x + width - 16
    green = (30, 255, 30)
    white = (235, 235, 235)
    muted = (165, 165, 165)
    counted_color = (0, 210, 0)
    return_color = (0, 0, 255)
    tracking_color = (255, 170, 0)

    def text(value: str, y: int, color=white, scale: float = 0.52, thickness: int = 1) -> None:
        cv2.putText(canvas, value, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)

    def divider(y: int) -> None:
        cv2.line(canvas, (x, y), (panel_right, y), (55, 55, 55), 1)

    # Layout compacto: cabe inteiro mesmo com webcams 640x480.
    text(str(snap["camera_name"])[:28], 28, white, 0.54, 2)
    text("CONTAGEM", 55, white, 0.58, 2)
    divider(64)
    text(f"CONTADOS: {snap['total_contado']}", 88, green, 0.57, 2)
    text(f"NO FRAME: {snap['animais_no_frame_agora']}", 113, green, 0.53, 2)
    text(f"RETORNOS: {snap['retornos_esquerda_para_direita']}", 138, green, 0.53, 2)

    text("DESEMPENHO", 174, white, 0.55, 2)
    divider(184)
    text(f"FPS camera: {snap['fps_camera']:.1f}", 208, green, 0.50, 2)
    text(f"FPS IA: {snap['fps_ia']:.1f}", 232, green, 0.50, 2)
    text(f"Latencia IA: {snap['latencia_ia_ms']:.0f} ms", 256, green, 0.48, 2)

    text("SESSAO", 292, white, 0.55, 2)
    divider(302)
    text(f"ID: {snap['session_id']}", 326, green, 0.52, 2)

    text("BOXES", 362, white, 0.55, 2)
    divider(372)
    legend = [("Rastreando", tracking_color), ("Contado", counted_color), ("Retorno", return_color)]
    ly = 399
    for label, color in legend:
        cv2.rectangle(canvas, (x, ly - 11), (x + 16, ly + 5), color, -1)
        cv2.putText(canvas, label, (x + 26, ly + 3), cv2.FONT_HERSHEY_SIMPLEX, 0.47, muted, 1, cv2.LINE_AA)
        ly += 27

    return canvas


class InferenceCoordinator:
    """Evita que varias instancias do YOLO saturem a CPU ao mesmo tempo."""

    def __init__(self, max_concurrent: int = 1) -> None:
        self._semaphore = threading.Semaphore(max(1, int(max_concurrent)))

    def run(self, callback):
        queued_at = time.perf_counter()
        self._semaphore.acquire()
        wait_ms = (time.perf_counter() - queued_at) * 1000.0
        try:
            return callback(), wait_ms
        finally:
            self._semaphore.release()


def configure_runtime(cfg: dict[str, Any]) -> int:
    """Configura bibliotecas numericas para nao disputar todos os nucleos da CPU."""
    perf = cfg.get("performance", {})
    cv_threads = int(perf.get("opencv_threads", 1))
    cv2.setNumThreads(cv_threads)

    requested = int(perf.get("torch_threads", 0))
    if requested <= 0:
        cpu_count = os.cpu_count() or 4
        # Metade dos nucleos, limitado a 4, deixa folga para captura, API e interface.
        requested = max(1, min(4, cpu_count // 2))

    try:
        import torch

        torch.set_num_threads(requested)
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            # Pode ocorrer se outra operacao paralela ja tiver sido inicializada.
            pass
    except Exception as exc:
        print(f"[performance] Aviso ao configurar threads do PyTorch: {exc}")

    return requested


class CameraWorker:
    def __init__(
        self,
        camera_cfg: dict[str, Any],
        cfg: dict[str, Any],
        db: EventDatabase,
        inference_coordinator: InferenceCoordinator,
    ) -> None:
        self.camera_cfg = camera_cfg
        self.cfg = cfg
        self.db = db
        self.inference_coordinator = inference_coordinator
        self.camera_id = str(camera_cfg["id"])
        self.camera_name = str(camera_cfg["name"])
        self.state = SharedState(
            camera_id=self.camera_id,
            camera_name=self.camera_name,
            max_events=int(cfg["persistence"]["max_api_events"]),
        )
        self.frames = LiveFrameStore()
        gate = camera_cfg["gate"]
        self.counter = GateCounter(
            left_x=float(gate["left_x"]),
            right_x=float(gate["right_x"]),
            stable_frames=int(gate["stable_frames"]),
            stale_after_frames=int(gate["stale_after_frames"]),
        )
        self.track_visual_status: dict[int, str] = {}
        self.track_visual_last_seen: dict[int, int] = {}
        self._runtime_lock = threading.RLock()
        self._visual_lock = threading.RLock()
        self._latest_visuals: list[dict[str, Any]] = []
        self._latest_visuals_at = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._render_thread: threading.Thread | None = None
        self._camera: LatestFrameCamera | None = None
        self._evidence: EvidenceRecorder | None = None

        session_id = self.db.start_session(self.camera_id, "inicio do programa")
        self.state.reset_counters(session_id=session_id)

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name=f"camera-worker-{self.camera_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        if self._render_thread and self._render_thread.is_alive():
            self._render_thread.join(timeout=2.0)

    def reset(self) -> int:
        with self._runtime_lock:
            self.counter.reset()
            self.track_visual_status.clear()
            self.track_visual_last_seen.clear()
            with self._visual_lock:
                self._latest_visuals.clear()
                self._latest_visuals_at = 0.0
            session_id = self.db.start_session(self.camera_id, "reset via API")
            self.state.reset_counters(session_id=session_id)
            return session_id

    def api_context(self) -> dict[str, Any]:
        return {"state": self.state, "frames": self.frames, "reset": self.reset}

    @staticmethod
    def _draw_visuals(frame, visuals: list[dict[str, Any]]) -> None:
        for visual in visuals:
            status = visual["status"]
            if status == "counted":
                box_color = (0, 210, 0)
                status_label = "CONTADO"
            elif status == "returned":
                box_color = (0, 0, 255)
                status_label = "RETORNO"
            else:
                box_color = (255, 170, 0)
                status_label = ""

            gx1, gy1, gx2, gy2 = visual["bbox"]
            ax, ay = visual["anchor"]
            cv2.rectangle(
                frame,
                (gx1, gy1),
                (gx2, gy2),
                box_color,
                3 if status_label else 2,
            )
            cv2.circle(frame, (ax, ay), 5, box_color, -1)
            box_label = f"ID {visual['track_id']} {visual['confidence']:.2f}"
            if status_label:
                box_label += f" | {status_label}"
            cv2.putText(
                frame,
                box_label,
                (gx1, max(18, gy1 - 7)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.52,
                box_color if status_label else (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

    def _visuals_for_render(self) -> list[dict[str, Any]]:
        max_age = float(self.cfg.get("display", {}).get("max_box_age_ms", 700)) / 1000.0
        with self._visual_lock:
            if time.monotonic() - self._latest_visuals_at > max_age:
                return []
            return [dict(item) for item in self._latest_visuals]

    def _render_loop(self) -> None:
        if self._camera is None or self._evidence is None:
            return

        preview_fps = max(5, int(self.cfg.get("display", {}).get("preview_fps", 20)))
        preview_interval = 1.0 / preview_fps
        jpeg_quality = int(self.cfg["api"].get("jpeg_quality", 75))
        stream_fps = max(1, int(self.cfg["api"].get("stream_fps", 8)))
        jpeg_interval = 1.0 / stream_fps
        last_jpeg_at = 0.0
        last_rendered_frame_id = -1

        while not self._stop.is_set():
            loop_started = time.perf_counter()
            frame_id, frame = self._camera.read()
            if frame is not None and frame_id != last_rendered_frame_id:
                last_rendered_frame_id = frame_id
                # O buffer de evidencias acompanha o video, nao o FPS da IA.
                self._evidence.push(frame)

                display = frame.copy()
                _, roi_box = roi_crop(display, self.camera_cfg["roi"])
                draw_gate(display, roi_box, self.camera_cfg["gate"])
                self._draw_visuals(display, self._visuals_for_render())

                self.state.update_metrics(fps_camera=self._camera.fps)
                window_frame = compose_display(
                    display.copy(),
                    self.state.snapshot(),
                    self.cfg.get("display", {}),
                )
                self.frames.update_display(window_frame)

                now = time.perf_counter()
                if now - last_jpeg_at >= jpeg_interval:
                    api_frame = (
                        window_frame
                        if bool(self.cfg.get("api", {}).get("include_sidebar", False))
                        else display
                    )
                    ok, encoded = cv2.imencode(
                        ".jpg",
                        api_frame,
                        [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality],
                    )
                    if ok:
                        self.frames.update_jpeg(encoded.tobytes())
                        last_jpeg_at = now

            elapsed = time.perf_counter() - loop_started
            remaining = preview_interval - elapsed
            if remaining > 0:
                self._stop.wait(remaining)
            else:
                time.sleep(0.001)

    def _run(self) -> None:
        model_cfg = self.cfg["model"]
        tracker = resolve_tracker(str(model_cfg["tracker"]))
        target_inference_fps = max(0.5, float(self.camera_cfg.get("inference_fps", 6.0)))
        inference_interval = 1.0 / target_inference_fps

        try:
            # Um modelo por camera preserva o estado do ByteTrack de cada fonte.
            # As inferencias sao coordenadas globalmente para nao saturar a CPU.
            model = YOLO(str(model_cfg["path"]))
            self._camera = LatestFrameCamera(
                source=self.camera_cfg["source"],
                width=int(self.camera_cfg.get("width", 0)) or None,
                height=int(self.camera_cfg.get("height", 0)) or None,
                fps=int(self.camera_cfg.get("fps", 0)) or None,
                backend=str(self.camera_cfg.get("backend", "auto")),
                fourcc=str(self.camera_cfg.get("fourcc", "MJPG")),
            ).start()

            evidence_dir = resolve_project_path(self.cfg["evidence"]["directory"]) / self.camera_id
            self._evidence = EvidenceRecorder(
                directory=evidence_dir,
                enabled=bool(self.cfg["evidence"]["enabled"]),
                save_snapshot=bool(self.cfg["evidence"]["save_snapshot"]),
                save_clip=bool(self.cfg["evidence"]["save_clip"]),
                pre_seconds=float(self.cfg["evidence"]["pre_seconds"]),
                post_seconds=float(self.cfg["evidence"]["post_seconds"]),
                clip_fps=float(self.cfg["evidence"]["clip_fps"]),
                on_clip_ready=lambda event_id, path: self.db.update_evidence(event_id, clip_path=path),
            )

            self.state.update_metrics(
                sistema_rodando=True,
                tracker=str(model_cfg["tracker"]),
                modelo=str(model_cfg["path"]),
                ultimo_erro=None,
                resolucao_camera=f"{self._camera.actual_width}x{self._camera.actual_height}",
                fps_camera_configurado=self._camera.actual_capture_fps,
                fps_ia_alvo=target_inference_fps,
            )

            self._render_thread = threading.Thread(
                target=self._render_loop,
                name=f"camera-render-{self.camera_id}",
                daemon=True,
            )
            self._render_thread.start()

            last_inference_frame_id = -1
            inference_index = 0
            inference_count = 0
            inference_mark = time.perf_counter()
            inference_fps = 0.0
            next_inference_at = 0.0

            print(
                f"[{self.camera_id}] camera aberta em "
                f"{self._camera.actual_width}x{self._camera.actual_height} "
                f"({self._camera.actual_capture_fps:.1f} FPS solicitado/negociado)"
            )

            while not self._stop.is_set():
                now = time.perf_counter()
                if now < next_inference_at:
                    self._stop.wait(min(0.01, next_inference_at - now))
                    continue

                frame_id, frame = self._camera.read()
                if frame is None or frame_id == last_inference_frame_id:
                    time.sleep(0.002)
                    continue

                last_inference_frame_id = frame_id
                next_inference_at = now + inference_interval
                inference_index += 1

                crop, roi_box = roi_crop(frame, self.camera_cfg["roi"])
                track_kwargs = dict(
                    source=crop,
                    persist=True,
                    tracker=tracker,
                    classes=list(model_cfg["classes"]),
                    conf=float(model_cfg["confidence"]),
                    imgsz=int(model_cfg["imgsz"]),
                    verbose=False,
                )
                if model_cfg.get("device") not in (None, "", "auto"):
                    track_kwargs["device"] = model_cfg["device"]

                started = time.perf_counter()
                results, queue_wait_ms = self.inference_coordinator.run(
                    lambda: model.track(**track_kwargs)
                )
                latency_ms = (time.perf_counter() - started) * 1000.0

                inference_count += 1
                mark_now = time.perf_counter()
                if mark_now - inference_mark >= 1.0:
                    inference_fps = inference_count / (mark_now - inference_mark)
                    inference_count = 0
                    inference_mark = mark_now

                detections = 0
                current_visuals: list[dict[str, Any]] = []
                pending_events: list[dict[str, Any]] = []

                if results:
                    boxes = results[0].boxes
                    if boxes is not None and boxes.id is not None:
                        xyxy = boxes.xyxy.cpu().tolist()
                        ids = boxes.id.int().cpu().tolist()
                        confs = boxes.conf.cpu().tolist()
                        detections = len(ids)
                        off_x, off_y = roi_box[0], roi_box[1]
                        roi_width = max(1, roi_box[2] - roi_box[0])

                        for bbox, track_id, confidence in zip(xyxy, ids, confs):
                            x1, y1, x2, y2 = bbox
                            event = self.counter.update(
                                track_id=int(track_id),
                                bbox=(x1, y1, x2, y2),
                                frame_width=roi_width,
                                confidence=float(confidence),
                                frame_index=inference_index,
                            )

                            tid = int(track_id)
                            with self._runtime_lock:
                                self.track_visual_last_seen[tid] = inference_index
                                if event:
                                    self.track_visual_status[tid] = (
                                        "counted" if event["contabilizado"] else "returned"
                                    )
                                visual_status = self.track_visual_status.get(tid, "tracking")

                            gx1, gy1 = int(x1 + off_x), int(y1 + off_y)
                            gx2, gy2 = int(x2 + off_x), int(y2 + off_y)
                            current_visuals.append(
                                {
                                    "track_id": tid,
                                    "confidence": float(confidence),
                                    "status": visual_status,
                                    "bbox": (gx1, gy1, gx2, gy2),
                                    "anchor": (
                                        int((x1 + x2) / 2 + off_x),
                                        int(y2 + off_y),
                                    ),
                                }
                            )
                            if event:
                                pending_events.append(event)

                self.counter.cleanup(inference_index)
                stale_after = int(self.camera_cfg["gate"]["stale_after_frames"])
                with self._runtime_lock:
                    stale_ids = [
                        tid
                        for tid, seen_at in self.track_visual_last_seen.items()
                        if inference_index - seen_at > stale_after
                    ]
                    for tid in stale_ids:
                        self.track_visual_last_seen.pop(tid, None)
                        self.track_visual_status.pop(tid, None)

                with self._visual_lock:
                    self._latest_visuals = current_visuals
                    self._latest_visuals_at = time.monotonic()

                # Persistencia/evidencia so ocorre quando ha um cruzamento real.
                if pending_events:
                    evidence_frame = frame.copy()
                    draw_gate(evidence_frame, roi_box, self.camera_cfg["gate"])
                    self._draw_visuals(evidence_frame, current_visuals)
                    for event in pending_events:
                        current_session = int(self.state.snapshot()["session_id"])
                        event_id = self.db.insert_event(current_session, self.camera_id, event)
                        label = "contado" if event["contabilizado"] else "retorno"
                        snapshot_path, clip_path = self._evidence.start_event(
                            event_id,
                            evidence_frame,
                            label,
                        )
                        self.db.update_evidence(event_id, snapshot_path=snapshot_path)
                        event.update(
                            {
                                "id": event_id,
                                "camera_id": self.camera_id,
                                "session_id": current_session,
                                "snapshot_path": snapshot_path,
                                "clip_path": clip_path,
                            }
                        )
                        self.state.register_event(event)

                self.state.update_metrics(
                    animais_no_frame_agora=detections,
                    fps_ia=inference_fps,
                    fps_camera=self._camera.fps,
                    latencia_ia_ms=latency_ms,
                    espera_fila_ia_ms=queue_wait_ms,
                )

        except Exception as exc:
            self.state.update_metrics(
                sistema_rodando=False,
                animais_no_frame_agora=0,
                ultimo_erro=f"{type(exc).__name__}: {exc}",
            )
            print(f"[{self.camera_id}] ERRO: {type(exc).__name__}: {exc}")
        finally:
            self._stop.set()
            self.state.update_metrics(sistema_rodando=False, animais_no_frame_agora=0)
            if self._render_thread and self._render_thread.is_alive():
                self._render_thread.join(timeout=2.0)
            if self._evidence is not None:
                self._evidence.close()
            if self._camera is not None:
                self._camera.stop()



def main() -> int:
    load_dotenv(BASE_DIR / ".env")
    args = parse_args()
    cfg = load_config(args.config)

    rebano_api_url = os.getenv("REBANO_API_URL", "http://localhost:5148").rstrip("/")
    jwt_secret = os.getenv("CONTAGEM_JWT_SECRET")
    integration_key = os.getenv("CONTAGEM_INTEGRATION_KEY")
    admin_user = os.getenv("CONTAGEM_ADMIN_USER", "admin")
    admin_password = os.getenv("CONTAGEM_ADMIN_PASSWORD")

    missing = []
    if not jwt_secret:
        missing.append("CONTAGEM_JWT_SECRET")
    if not integration_key:
        missing.append("CONTAGEM_INTEGRATION_KEY")
    if not admin_password:
        missing.append("CONTAGEM_ADMIN_PASSWORD")
    if missing:
        raise RuntimeError(
            "Variaveis obrigatorias ausentes no .env: " + ", ".join(missing)
        )

    auth_service = AuthService(
        rebano_api_url=rebano_api_url,
        jwt_secret=jwt_secret,
        integration_key=integration_key,
        admin_user=admin_user,
        admin_password=admin_password,
    )

    torch_threads = configure_runtime(cfg)
    max_concurrent = int(cfg.get("performance", {}).get("max_concurrent_inferences", 1))
    inference_coordinator = InferenceCoordinator(max_concurrent)

    db = EventDatabase(resolve_project_path(cfg["persistence"]["database"]))
    workers = [
        CameraWorker(camera_cfg, cfg, db, inference_coordinator)
        for camera_cfg in cfg["video"]["cameras"]
        if bool(camera_cfg.get("enabled", True))
    ]

    camera_contexts = {worker.camera_id: worker.api_context() for worker in workers}

    def reset_all() -> dict[str, int]:
        return {worker.camera_id: worker.reset() for worker in workers}

    app = create_app(
        camera_contexts,
        db,
        reset_all,
        auth_service=auth_service,
        integration_key=integration_key,
        stream_fps=int(cfg["api"]["stream_fps"]),
    )
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=str(cfg["app"]["host"]),
            port=int(cfg["app"]["port"]),
            log_level="info",
        )
    )
    api_thread = threading.Thread(target=server.run, name="api-server", daemon=True)
    api_thread.start()

    for worker in workers:
        worker.start()

    port = int(cfg["app"]["port"])
    print("\nContagemSys Web V5 iniciado.")
    print(f"Login web:     http://127.0.0.1:{port}/")
    print(f"Admin web:     http://127.0.0.1:{port}/admin")
    print(f"Swagger local: http://127.0.0.1:{port}/docs")
    print(f"Health:        http://127.0.0.1:{port}/health")
    print("Para outra maquina, troque 127.0.0.1 pelo IPv4 desta maquina.")
    print(
        f"Performance: {max_concurrent} inferencia(s) simultanea(s), "
        f"PyTorch com {torch_threads} thread(s)."
    )
    print("Cameras configuradas:")
    for worker in workers:
        print(f"  - {worker.camera_id}: {worker.camera_name} (source={worker.camera_cfg['source']})")
    if cfg["app"].get("show_window", True):
        print("Pressione Q em qualquer janela para encerrar todas as cameras.")

    last_display_versions = {worker.camera_id: -1 for worker in workers}

    try:
        while True:
            if cfg["app"].get("show_window", True):
                updated_any = False
                for worker in workers:
                    version, display = worker.frames.display()
                    if display is not None and version != last_display_versions[worker.camera_id]:
                        last_display_versions[worker.camera_id] = version
                        updated_any = True
                        cv2.imshow(f"{cfg['app']['name']} - {worker.camera_name}", display)
                if cv2.waitKey(1 if updated_any else 5) & 0xFF in (ord("q"), ord("Q")):
                    break
            else:
                time.sleep(0.15)

            if not api_thread.is_alive():
                print("Servidor da API foi encerrado inesperadamente.")
                break
    except KeyboardInterrupt:
        pass
    finally:
        for worker in workers:
            worker.stop()
        server.should_exit = True
        api_thread.join(timeout=3.0)
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
