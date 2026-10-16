"""Associacao multiobjeto leve, independente dos IDs opcionais do ByteTrack.

YOLO.predict() devolve caixas mesmo quando o tracker da Ultralytics nao inicializa.
As associacoes sao independentes por instancia/camera, com memoria curta e
predicao linear de movimento. Nao identifica pessoas biometricamente.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Sequence


@dataclass(frozen=True)
class Detection:
    bbox: tuple[float, float, float, float]
    confidence: float
    class_id: int = 0


@dataclass(frozen=True)
class TrackedDetection:
    track_id: int
    bbox: tuple[float, float, float, float]
    confidence: float
    class_id: int


@dataclass
class _Memory:
    bbox: tuple[float, float, float, float]
    class_id: int
    seen_at: float
    vx: float = 0.0
    vy: float = 0.0


def _center(box):
    return (0.5 * (box[0] + box[2]), 0.5 * (box[1] + box[3]))


def _iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    aa = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    ab = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    return intersection / (aa + ab - intersection) if aa + ab > intersection else 0.0


class MultiObjectTracker:
    """Uma instancia por camera; IDs sao estaveis durante passagens curtas."""

    def __init__(self, max_missing_seconds: float = 3.5) -> None:
        self.max_missing_seconds = float(max_missing_seconds)
        self._tracks: dict[int, _Memory] = {}
        self._next_id = 1

    def reset(self) -> None:
        self._tracks.clear()
        # Nao reciclar IDs durante a mesma sessao para evitar confundir eventos.

    def update(
        self, detections: Sequence[Detection], timestamp: float | None = None
    ) -> list[TrackedDetection]:
        now = time.monotonic() if timestamp is None else float(timestamp)
        self._tracks = {
            tid: state for tid, state in self._tracks.items()
            if now - state.seen_at <= self.max_missing_seconds
        }
        scores: list[tuple[float, int, int]] = []
        for index, det in enumerate(detections):
            cx, cy = _center(det.bbox)
            for tid, mem in self._tracks.items():
                if mem.class_id != det.class_id:
                    continue
                dt = max(0, now - mem.seen_at)
                px, py = _center(mem.bbox)
                # Movimento extrapolado limitado; evita saltos quando o video para.
                px += mem.vx * min(dt, 0.8)
                py += mem.vy * min(dt, 0.8)
                previous_size = math.hypot(mem.bbox[2] - mem.bbox[0], mem.bbox[3] - mem.bbox[1])
                current_size = math.hypot(det.bbox[2] - det.bbox[0], det.bbox[3] - det.bbox[1])
                scale = max(35.0, previous_size, current_size)
                distance = math.hypot(cx - px, cy - py) / scale
                overlap = _iou(det.bbox, mem.bbox)
                if distance > 1.8 and overlap < 0.015:
                    continue
                # Quando duas pessoas se cruzam, IoU puro troca os IDs.
                # A direcao anterior funciona como sinal extra de associacao.
                displacement_x = cx - _center(mem.bbox)[0]
                displacement_y = cy - _center(mem.bbox)[1]
                direction_penalty = 0.0
                if abs(mem.vx) > 12 and mem.vx * displacement_x < -0.08 * scale * abs(mem.vx):
                    direction_penalty += 1.25
                if abs(mem.vy) > 12 and mem.vy * displacement_y < -0.08 * scale * abs(mem.vy):
                    direction_penalty += 1.25
                size_change = abs(math.log(max(current_size, 1) / max(previous_size, 1)))
                # Distancia predita prevalece sobre sobreposicao do frame anterior.
                cost = (1.65 * distance + 0.25 * (1.0 - overlap) +
                        0.20 * size_change + direction_penalty)
                scores.append((cost, tid, index))

        scores.sort()
        matches: dict[int, int] = {}
        used_ids: set[int] = set()
        for _, tid, index in scores:
            if index not in matches and tid not in used_ids:
                matches[index] = tid
                used_ids.add(tid)

        output: list[TrackedDetection] = []
        for index, det in enumerate(detections):
            tid = matches.get(index)
            if tid is None:
                tid = self._next_id
                self._next_id += 1
                self._tracks[tid] = _Memory(det.bbox, det.class_id, now)
            else:
                mem = self._tracks[tid]
                dt = now - mem.seen_at
                if dt > 0.001:
                    prev_cx, prev_cy = _center(mem.bbox)
                    cx, cy = _center(det.bbox)
                    instantaneous_vx = (cx - prev_cx) / dt
                    instantaneous_vy = (cy - prev_cy) / dt
                    mem.vx = 0.45 * mem.vx + 0.55 * instantaneous_vx
                    mem.vy = 0.45 * mem.vy + 0.55 * instantaneous_vy
                mem.bbox = det.bbox
                mem.seen_at = now
            output.append(TrackedDetection(tid, det.bbox, det.confidence, det.class_id))
        return output


def boxes_to_detections(boxes) -> list[Detection]:
    """Le TODAS as deteccoes YOLO (boxes.id nao e necessario)."""
    if boxes is None:
        return []
    xyxy = boxes.xyxy.cpu().tolist()
    confidences = boxes.conf.cpu().tolist()
    classes = boxes.cls.int().cpu().tolist() if getattr(boxes, 'cls', None) is not None else [0] * len(xyxy)
    return [
        Detection(tuple(map(float, box)), float(conf), int(cls))
        for box, conf, cls in zip(xyxy, confidences, classes)
    ]
