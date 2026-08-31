from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

import cv2
import uvicorn
from ultralytics import YOLO

from api import create_app
from camera_stream import LatestFrameCamera
from config import load_config, resolve_project_path, resolve_tracker
from counting import GateCounter
from evidence import EvidenceRecorder
from persistence import EventDatabase
from state import SharedState

BASE_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sistema de contagem direcional V3")
    parser.add_argument("--config", default=str(BASE_DIR / "config.yaml"))
    return parser.parse_args()


def roi_crop(frame, roi_cfg: dict):
    h, w = frame.shape[:2]
    if not roi_cfg.get("enabled", False):
        return frame, (0, 0, w, h)
    x1 = int(w * roi_cfg["x1"])
    y1 = int(h * roi_cfg["y1"])
    x2 = int(w * roi_cfg["x2"])
    y2 = int(h * roi_cfg["y2"])
    return frame[y1:y2, x1:x2], (x1, y1, x2, y2)


def draw_gate(frame, roi_box: tuple[int, int, int, int], gate_cfg: dict) -> None:
    x1, y1, x2, y2 = roi_box
    width = x2 - x1
    left = x1 + int(width * gate_cfg["left_x"])
    right = x1 + int(width * gate_cfg["right_x"])
    cv2.rectangle(frame, (x1, y1), (x2 - 1, y2 - 1), (120, 120, 120), 1)
    cv2.line(frame, (left, y1), (left, y2), (0, 200, 255), 2)
    cv2.line(frame, (right, y1), (right, y2), (0, 200, 255), 2)
    cv2.putText(frame, "LEFT", (x1 + 8, y1 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
    cv2.putText(frame, "GATE", (left + 8, y1 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
    cv2.putText(frame, "RIGHT", (right + 8, y1 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)


def draw_hud(frame, snap: dict) -> None:
    """Fallback do HUD quando a barra lateral estiver desativada."""
    lines = [
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


def compose_display(frame, snap: dict, display_cfg: dict) -> "cv2.typing.MatLike":
    """Adiciona um painel preto ao lado do video, sem cobrir a imagem."""
    sidebar = display_cfg.get("sidebar", {})
    if not sidebar.get("enabled", True):
        draw_hud(frame, snap)
        return frame

    width = max(230, int(sidebar.get("width", 300)))
    position = str(sidebar.get("position", "left")).lower()

    if position == "right":
        canvas = cv2.copyMakeBorder(
            frame, 0, 0, 0, width, cv2.BORDER_CONSTANT, value=(0, 0, 0)
        )
        panel_x = frame.shape[1]
    else:
        canvas = cv2.copyMakeBorder(
            frame, 0, 0, width, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0)
        )
        panel_x = 0

    x = panel_x + 20
    panel_right = panel_x + width - 20
    green = (30, 255, 30)
    white = (235, 235, 235)
    muted = (165, 165, 165)
    counted_color = (0, 210, 0)
    return_color = (0, 0, 255)
    tracking_color = (255, 170, 0)

    def text(value: str, y: int, color=white, scale: float = 0.58, thickness: int = 1) -> None:
        cv2.putText(
            canvas, value, (x, y), cv2.FONT_HERSHEY_SIMPLEX,
            scale, color, thickness, cv2.LINE_AA
        )

    def divider(y: int) -> None:
        cv2.line(canvas, (x, y), (panel_right, y), (55, 55, 55), 1)

    text("CONTAGEM", 38, white, 0.68, 2)
    divider(52)
    text(f"CONTADOS: {snap['total_contado']}", 84, green, 0.66, 2)
    text(f"NO FRAME: {snap['animais_no_frame_agora']}", 114, green, 0.62, 2)
    text(f"RETORNOS: {snap['retornos_esquerda_para_direita']}", 144, green, 0.62, 2)

    text("DESEMPENHO", 194, white, 0.62, 2)
    divider(208)
    text(f"FPS camera: {snap['fps_camera']:.1f}", 239, green, 0.56, 2)
    text(f"FPS IA: {snap['fps_ia']:.1f}", 268, green, 0.56, 2)
    text(f"Latencia IA: {snap['latencia_ia_ms']:.1f} ms", 297, green, 0.53, 2)

    text("SESSAO", 347, white, 0.62, 2)
    divider(361)
    text(f"ID: {snap['session_id']}", 392, green, 0.58, 2)

    # Legenda das caixas: ajuda a entender imediatamente o estado de cada track.
    text("BOXES", 442, white, 0.62, 2)
    divider(456)
    legend = [
        ("Rastreando", tracking_color),
        ("Contado", counted_color),
        ("Retorno", return_color),
    ]
    ly = 487
    for label, color in legend:
        cv2.rectangle(canvas, (x, ly - 13), (x + 18, ly + 5), color, -1)
        cv2.putText(
            canvas, label, (x + 30, ly + 3), cv2.FONT_HERSHEY_SIMPLEX,
            0.52, muted, 1, cv2.LINE_AA
        )
        ly += 31

    return canvas


def main() -> int:
    args = parse_args()
    cfg = load_config(args.config)

    db = EventDatabase(resolve_project_path(cfg["persistence"]["database"]))
    state = SharedState(max_events=int(cfg["persistence"]["max_api_events"]))
    counter = GateCounter(
        left_x=float(cfg["gate"]["left_x"]),
        right_x=float(cfg["gate"]["right_x"]),
        stable_frames=int(cfg["gate"]["stable_frames"]),
        stale_after_frames=int(cfg["gate"]["stale_after_frames"]),
    )

    # Estado visual separado da logica de contagem. A cor permanece enquanto
    # o ID continuar ativo, em vez de piscar apenas no frame do evento.
    track_visual_status: dict[int, str] = {}
    track_visual_last_seen: dict[int, int] = {}

    reset_lock = threading.Lock()

    def reset_system() -> int:
        with reset_lock:
            counter.reset()
            track_visual_status.clear()
            track_visual_last_seen.clear()
            session_id = db.start_session("reset via API")
            state.reset_counters(session_id=session_id)
            return session_id

    session_id = db.start_session("inicio do programa")
    state.reset_counters(session_id=session_id)

    app = create_app(state, db, reset_system)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=str(cfg["app"]["host"]),
            port=int(cfg["app"]["port"]),
            log_level="warning",
        )
    )
    api_thread = threading.Thread(target=server.run, name="api-server", daemon=True)
    api_thread.start()

    model_cfg = cfg["model"]
    tracker = resolve_tracker(str(model_cfg["tracker"]))
    model = YOLO(str(model_cfg["path"]))

    source = cfg["video"]["source"]
    camera = LatestFrameCamera(
        source=source,
        width=int(cfg["video"].get("width", 0)) or None,
        height=int(cfg["video"].get("height", 0)) or None,
    ).start()

    evidence = EvidenceRecorder(
        directory=resolve_project_path(cfg["evidence"]["directory"]),
        enabled=bool(cfg["evidence"]["enabled"]),
        save_snapshot=bool(cfg["evidence"]["save_snapshot"]),
        save_clip=bool(cfg["evidence"]["save_clip"]),
        pre_seconds=float(cfg["evidence"]["pre_seconds"]),
        post_seconds=float(cfg["evidence"]["post_seconds"]),
        clip_fps=float(cfg["evidence"]["clip_fps"]),
        on_clip_ready=lambda event_id, path: db.update_evidence(event_id, clip_path=path),
    )

    state.update_metrics(
        sistema_rodando=True,
        tracker=str(model_cfg["tracker"]),
        modelo=str(model_cfg["path"]),
    )

    print(f"Swagger:              http://{cfg['app']['host']}:{cfg['app']['port']}/docs")
    print(f"Contagem atual:       http://{cfg['app']['host']}:{cfg['app']['port']}/contagem/atual")
    print(f"Eventos de passagem: http://{cfg['app']['host']}:{cfg['app']['port']}/contagem/eventos")
    print("Pressione Q na janela para sair.")

    last_frame_id = -1
    frame_index = 0
    inference_count = 0
    inference_mark = time.perf_counter()
    inference_fps = 0.0
    last_annotated = None
    stride = max(1, int(cfg["video"].get("inference_stride", 1)))

    try:
        while True:
            frame_id, frame = camera.read()
            if frame is None or frame_id == last_frame_id:
                time.sleep(0.002)
                continue
            last_frame_id = frame_id
            frame_index += 1
            evidence.push(frame)

            display = frame.copy()
            crop, roi_box = roi_crop(frame, cfg["roi"])
            draw_gate(display, roi_box, cfg["gate"])

            if frame_index % stride == 0:
                started = time.perf_counter()
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

                results = model.track(**track_kwargs)
                latency_ms = (time.perf_counter() - started) * 1000.0
                inference_count += 1
                now = time.perf_counter()
                if now - inference_mark >= 1.0:
                    inference_fps = inference_count / (now - inference_mark)
                    inference_count = 0
                    inference_mark = now

                detections = 0
                if results:
                    result = results[0]
                    boxes = result.boxes
                    if boxes is not None and boxes.id is not None:
                        xyxy = boxes.xyxy.cpu().tolist()
                        ids = boxes.id.int().cpu().tolist()
                        confs = boxes.conf.cpu().tolist()
                        detections = len(ids)
                        off_x, off_y = roi_box[0], roi_box[1]
                        roi_width = max(1, roi_box[2] - roi_box[0])

                        for bbox, track_id, confidence in zip(xyxy, ids, confs):
                            x1, y1, x2, y2 = bbox
                            event = counter.update(
                                track_id=int(track_id),
                                bbox=(x1, y1, x2, y2),
                                frame_width=roi_width,
                                confidence=float(confidence),
                                frame_index=frame_index,
                            )

                            tid = int(track_id)
                            track_visual_last_seen[tid] = frame_index

                            if event:
                                # Verde = completou RIGHT -> CENTER -> LEFT e foi contado.
                                # Vermelho = completou LEFT -> CENTER -> RIGHT e foi retorno.
                                track_visual_status[tid] = (
                                    "counted" if event["contabilizado"] else "returned"
                                )

                            visual_status = track_visual_status.get(tid, "tracking")
                            if visual_status == "counted":
                                box_color = (0, 210, 0)
                                status_label = "CONTADO"
                            elif visual_status == "returned":
                                box_color = (0, 0, 255)
                                status_label = "RETORNO"
                            else:
                                box_color = (255, 170, 0)
                                status_label = ""

                            gx1, gy1, gx2, gy2 = int(x1 + off_x), int(y1 + off_y), int(x2 + off_x), int(y2 + off_y)
                            ax = int((x1 + x2) / 2 + off_x)
                            ay = int(y2 + off_y)
                            cv2.rectangle(display, (gx1, gy1), (gx2, gy2), box_color, 3 if status_label else 2)
                            cv2.circle(display, (ax, ay), 5, box_color, -1)

                            box_label = f"ID {track_id} {confidence:.2f}"
                            if status_label:
                                box_label += f" | {status_label}"
                            cv2.putText(
                                display,
                                box_label,
                                (gx1, max(18, gy1 - 7)),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.52,
                                box_color if status_label else (255, 255, 255),
                                2,
                                cv2.LINE_AA,
                            )

                            if event:
                                current_session = int(state.snapshot()["session_id"])
                                event_id = db.insert_event(current_session, event)
                                label = "contado" if event["contabilizado"] else "retorno"
                                snapshot_path, clip_path = evidence.start_event(event_id, display, label)
                                db.update_evidence(event_id, snapshot_path=snapshot_path)
                                event.update(
                                    {
                                        "id": event_id,
                                        "session_id": current_session,
                                        "snapshot_path": snapshot_path,
                                        "clip_path": clip_path,
                                    }
                                )
                                state.register_event(event)

                counter.cleanup(frame_index)

                # Evita acumular IDs antigos e impede que um ID reutilizado no futuro
                # herde a cor de uma entidade que ja saiu da cena.
                visual_stale_after = int(cfg["gate"]["stale_after_frames"])
                stale_visual_ids = [
                    tid for tid, seen_at in track_visual_last_seen.items()
                    if frame_index - seen_at > visual_stale_after
                ]
                for tid in stale_visual_ids:
                    track_visual_last_seen.pop(tid, None)
                    track_visual_status.pop(tid, None)

                state.update_metrics(
                    animais_no_frame_agora=detections,
                    fps_ia=inference_fps,
                    fps_camera=camera.fps,
                    latencia_ia_ms=latency_ms,
                )
                last_annotated = display.copy()
            else:
                state.update_metrics(fps_camera=camera.fps)
                if last_annotated is not None:
                    # Mostra o frame atual, mantendo gate/HUD atualizados; nao repete bbox antiga.
                    pass

            window_frame = compose_display(display, state.snapshot(), cfg.get("display", {}))

            if cfg["app"].get("show_window", True):
                cv2.imshow(str(cfg["app"]["name"]), window_frame)
                if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q")):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        state.update_metrics(sistema_rodando=False, animais_no_frame_agora=0)
        evidence.close()
        camera.stop()
        server.should_exit = True
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
