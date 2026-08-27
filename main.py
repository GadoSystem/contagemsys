"""Contador direcional de rebanho em tempo real.

Arquitetura v2:
  câmera (thread) -> sempre mantém apenas o frame mais novo
  IA/tracker (thread) -> processa o frame mais novo disponível, sem criar fila
  UI (thread principal) -> continua exibindo a webcam enquanto a IA trabalha
  contador -> soma SOMENTE cruzamentos DIREITA -> ESQUERDA
  FastAPI (thread) -> expõe contagem, eventos e reset

Para testar com pessoas use CLASSES_ALVO = [0].
Para bovinos no modelo COCO use CLASSES_ALVO = [19].
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import torch
import uvicorn
from ultralytics import YOLO

from api import app
from camera_stream import LeitorCamera
from counting import CrossingEvent, DirectionalLineCounter
from state import estado

# ============================================================================
# CONFIGURAÇÃO
# ============================================================================
BASE_DIR = Path(__file__).resolve().parent
FONTE_VIDEO = 0

# Modelo leve para tempo real. Para produção, substitua pelo seu best.pt treinado
# com imagens reais da câmera/porteira.
MODELO = "yolo26n.pt"

# COCO: 0=person (teste), 19=cow (produção inicial sem fine-tuning)
CLASSES_ALVO = [0]

# Padrão: leve e rápido. Se ainda houver muita troca de ID, use:
# TRACKER = str(BASE_DIR / "tracker_botsort_reid.yaml")
TRACKER = str(BASE_DIR / "tracker_bytetrack.yaml")

# IMPORTANTE no ByteTrack: conf baixa deixa o tracker recuperar detecções fracas.
# O arquivo tracker_bytetrack.yaml usa limiar maior para criar um NOVO ID.
CONFIANCA_DETECCAO = 0.15
IOU_NMS = 0.60
MAX_DETECCOES = 60

# 416 costuma ser um bom equilíbrio para webcam/CPU. Teste 320 em PCs fracos.
IMGSZ = 416
LARGURA_CAMERA = 640
ALTURA_CAMERA = 480
FPS_CAMERA_DESEJADO = 30

# Linha vertical no meio do vídeo. 0.50 = 50% da largura.
LINHA_X_RELATIVA = 0.50

# Faixa morta ao redor da linha. Evita que tremedeira/giro da bounding box conte.
MARGEM_LINHA_RELATIVA = 0.025

# Deslocamento horizontal mínimo para aceitar a trajetória como cruzamento real.
DESLOCAMENTO_MIN_RELATIVO = 0.07
MIN_FRAMES_TRACK = 3

# ============================================================================


@dataclass
class VisualDetection:
    track_id: int
    box: Tuple[int, int, int, int]
    confidence: float
    class_id: int
    status: str
    trail: List[Tuple[int, int]]


class ProcessadorVisao:
    def __init__(
        self,
        *,
        modelo: YOLO,
        camera: LeitorCamera,
        contador: DirectionalLineCounter,
        device,
        half: bool,
    ) -> None:
        self.modelo = modelo
        self.camera = camera
        self.contador = contador
        self.device = device
        self.half = half

        self._parar = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._deteccoes: List[VisualDetection] = []
        self._fps_ia = 0.0
        self._latencia_ms = 0.0
        self._processed_seq = 0
        self._erro: Optional[BaseException] = None

    def iniciar(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def parar(self) -> None:
        self._parar.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def snapshot_visual(self) -> Dict:
        with self._lock:
            return {
                "deteccoes": list(self._deteccoes),
                "fps_ia": self._fps_ia,
                "latencia_ms": self._latencia_ms,
                "processed_seq": self._processed_seq,
                "erro": self._erro,
            }

    def _loop(self) -> None:
        last_seq = -1
        reset_version = estado.reset_version()

        try:
            while not self._parar.is_set():
                current_reset = estado.reset_version()
                if current_reset != reset_version:
                    self.contador.reset()
                    reset_version = current_reset

                packet = self.camera.ultimo_pacote()
                if packet is None or packet.seq == last_seq:
                    time.sleep(0.001)
                    continue

                # A IA sempre salta direto para o frame mais recente. Se ela for
                # mais lenta que a câmera, frames intermediários são descartados.
                last_seq = packet.seq
                inicio = time.perf_counter()

                resultados = self.modelo.track(
                    packet.frame,
                    classes=CLASSES_ALVO,
                    conf=CONFIANCA_DETECCAO,
                    iou=IOU_NMS,
                    max_det=MAX_DETECCOES,
                    tracker=TRACKER,
                    imgsz=IMGSZ,
                    persist=True,
                    device=self.device,
                    half=self.half,
                    verbose=False,
                )

                terminou = time.perf_counter()
                tempo = max(terminou - inicio, 1e-6)
                fps_instantaneo = 1.0 / tempo
                self._fps_ia = (
                    fps_instantaneo
                    if self._fps_ia <= 0
                    else 0.85 * self._fps_ia + 0.15 * fps_instantaneo
                )
                self._latencia_ms = max(0.0, (terminou - packet.captured_at) * 1000.0)

                r = resultados[0]
                tracks_for_counter: List[Tuple[int, Tuple[int, int]]] = []
                raw_detections = []

                if r.boxes is not None and r.boxes.id is not None:
                    boxes = r.boxes
                    xyxy = boxes.xyxy.detach().cpu().tolist()
                    ids = boxes.id.detach().to("cpu").int().tolist()
                    confs = boxes.conf.detach().cpu().tolist()
                    classes = boxes.cls.detach().to("cpu").int().tolist()

                    for box, track_id, conf, class_id in zip(xyxy, ids, confs, classes):
                        x1, y1, x2, y2 = map(int, box)
                        # Para uma linha vertical, o x do centro da caixa é estável.
                        # No y usamos a base da caixa para a trilha ficar junto aos pés/patas.
                        point = (int((x1 + x2) / 2), int(y2))
                        tracks_for_counter.append((track_id, point))
                        raw_detections.append((track_id, (x1, y1, x2, y2), conf, class_id))

                events = self.contador.update_many(tracks_for_counter, packet.seq)
                for event in events:
                    self._registrar_evento(event, reset_version)

                deteccoes_visuais: List[VisualDetection] = []
                for track_id, box, conf, class_id in raw_detections:
                    deteccoes_visuais.append(
                        VisualDetection(
                            track_id=track_id,
                            box=box,
                            confidence=float(conf),
                            class_id=class_id,
                            status=self.contador.status_for(track_id),
                            trail=self.contador.trail_for(track_id),
                        )
                    )

                estado.atualizar(
                    total=self.contador.total_counted,
                    no_frame=len(raw_detections),
                    retornos=self.contador.reverse_crossings,
                    fps_ia=self._fps_ia,
                    fps_camera=self.camera.fps_captura,
                    latencia_ms=self._latencia_ms,
                    reset_version=reset_version,
                )

                with self._lock:
                    self._deteccoes = deteccoes_visuais
                    self._processed_seq = packet.seq
        except BaseException as exc:  # deixa o erro chegar à thread principal
            with self._lock:
                self._erro = exc
            estado.marcar_parado()

    @staticmethod
    def _registrar_evento(event: CrossingEvent, reset_version: int) -> None:
        estado.registrar_evento(
            {
                "track_id": event.track_id,
                "direcao": event.direction,
                "contabilizado": event.counted,
                "frame": event.frame_index,
                "ponto": {"x": event.point[0], "y": event.point[1]},
            },
            reset_version=reset_version,
        )


def iniciar_api() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")


def escolher_device():
    if torch.cuda.is_available():
        torch.backends.cudnn.benchmark = True
        nome = torch.cuda.get_device_name(0)
        print(f"GPU detectada: {nome} -> CUDA + FP16 habilitado")
        return 0, True
    print("GPU CUDA não detectada -> usando CPU")
    return "cpu", False


def desenhar_linha(frame, line_x: int, dead_zone_px: int) -> None:
    h, w = frame.shape[:2]
    topo = 92

    # Faixa morta: duas linhas finas; linha central: mais grossa.
    cv2.line(frame, (line_x - dead_zone_px, topo), (line_x - dead_zone_px, h), (100, 100, 100), 1)
    cv2.line(frame, (line_x + dead_zone_px, topo), (line_x + dead_zone_px, h), (100, 100, 100), 1)
    cv2.line(frame, (line_x, topo), (line_x, h), (0, 255, 255), 2)

    x_start = min(w - 15, line_x + min(130, w // 4))
    x_end = max(15, line_x - min(130, w // 4))
    cv2.arrowedLine(frame, (x_start, topo + 22), (x_end, topo + 22), (0, 255, 255), 2, tipLength=0.12)
    cv2.putText(
        frame,
        "CONTAR: DIREITA -> ESQUERDA",
        (max(8, line_x - 145), topo + 48),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (0, 255, 255),
        1,
        cv2.LINE_AA,
    )


def desenhar_deteccoes(frame, deteccoes: List[VisualDetection]) -> None:
    for det in deteccoes:
        x1, y1, x2, y2 = det.box
        if det.status == "contado":
            cor = (0, 220, 0)
        elif det.status == "retorno":
            cor = (0, 165, 255)
        else:
            cor = (255, 180, 0)

        cv2.rectangle(frame, (x1, y1), (x2, y2), cor, 2)
        label = f"ID {det.track_id} {det.confidence:.2f} {det.status}"
        cv2.putText(
            frame,
            label,
            (x1, max(108, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            cor,
            2,
            cv2.LINE_AA,
        )

        if len(det.trail) >= 2:
            for p1, p2 in zip(det.trail[:-1], det.trail[1:]):
                cv2.line(frame, p1, p2, cor, 2)


def desenhar_overlay(frame, snapshot: Dict) -> None:
    largura = frame.shape[1]
    cv2.rectangle(frame, (0, 0), (largura, 92), (0, 0, 0), -1)

    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    cv2.putText(frame, agora, (12, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2)

    linha1 = (
        f"CONTADOS: {snapshot['total_contado']}   |   "
        f"NO FRAME: {snapshot['animais_no_frame_agora']}   |   "
        f"RETORNOS: {snapshot['retornos_esquerda_para_direita']}"
    )
    cv2.putText(frame, linha1, (12, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0, 255, 0), 2)

    linha2 = (
        f"FPS camera: {snapshot['fps_camera']:.1f}   |   "
        f"FPS IA: {snapshot['fps_ia']:.1f}   |   "
        f"latencia IA: {snapshot['latencia_ia_ms']:.0f} ms"
    )
    cv2.putText(frame, linha2, (12, 78), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (220, 220, 220), 1)


def main() -> None:
    cv2.setUseOptimized(True)

    thread_api = threading.Thread(target=iniciar_api, daemon=True)
    thread_api.start()
    print("=" * 72)
    print("Swagger:              http://localhost:8000/docs")
    print("Contagem atual:       http://localhost:8000/contagem/atual")
    print("Eventos de passagem: http://localhost:8000/contagem/eventos")
    print("=" * 72)

    device, usar_half = escolher_device()

    print(f"Carregando modelo: {MODELO}")
    modelo = YOLO(MODELO)
    # Fuse Conv+BN em modelos PyTorch quando disponível; pequena redução de overhead.
    try:
        if str(MODELO).lower().endswith(".pt"):
            modelo.fuse()
    except Exception:
        pass

    print(f"Abrindo câmera: {FONTE_VIDEO!r}")
    camera = LeitorCamera(
        FONTE_VIDEO,
        largura_alvo=LARGURA_CAMERA,
        altura_alvo=ALTURA_CAMERA,
        fps_alvo=FPS_CAMERA_DESEJADO,
    ).iniciar()

    primeiro = None
    for _ in range(150):
        primeiro = camera.ultimo_pacote()
        if primeiro is not None:
            break
        time.sleep(0.05)
    if primeiro is None:
        camera.parar()
        raise RuntimeError("A câmera não entregou nenhum frame.")

    altura, largura = primeiro.frame.shape[:2]
    line_x = int(largura * LINHA_X_RELATIVA)
    dead_zone_px = max(8, int(largura * MARGEM_LINHA_RELATIVA))
    min_displacement_px = max(dead_zone_px * 2, int(largura * DESLOCAMENTO_MIN_RELATIVO))

    contador = DirectionalLineCounter(
        line_x=line_x,
        frame_width=largura,
        dead_zone_px=dead_zone_px,
        min_track_frames=MIN_FRAMES_TRACK,
        min_displacement_px=min_displacement_px,
    )

    processador = ProcessadorVisao(
        modelo=modelo,
        camera=camera,
        contador=contador,
        device=device,
        half=usar_half,
    ).iniciar()

    print(
        f"Sistema pronto: {largura}x{altura}, linha x={line_x}, tracker={TRACKER}.\n"
        "Passe da DIREITA para a ESQUERDA para somar. O inverso não soma.\n"
        "Pressione Q na janela para encerrar.\n"
    )

    try:
        while True:
            packet = camera.ultimo_pacote()
            if packet is None:
                time.sleep(0.002)
                continue

            visual = processador.snapshot_visual()
            if visual["erro"] is not None:
                raise RuntimeError("Falha na thread de visão") from visual["erro"]

            # A UI usa o frame NOVO da câmera e sobrepõe a última inferência pronta.
            # Assim a janela continua fluida mesmo quando a IA roda a menos FPS.
            frame = packet.frame
            desenhar_linha(frame, line_x, dead_zone_px)
            desenhar_deteccoes(frame, visual["deteccoes"])
            desenhar_overlay(frame, estado.snapshot())

            cv2.imshow("Contagem direcional de rebanho - Q para sair", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q")):
                break
    finally:
        processador.parar()
        camera.parar()
        estado.marcar_parado()
        cv2.destroyAllWindows()
        print(f"Encerrado. Total contabilizado: {estado.snapshot()['total_contado']}")


if __name__ == "__main__":
    main()
