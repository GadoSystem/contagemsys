from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Literal

Zone = Literal["LEFT", "CENTER", "RIGHT"]


@dataclass
class TrackState:
    candidate_zone: Zone | None = None
    candidate_hits: int = 0
    stable_zone: Zone | None = None
    origin_side: Zone | None = None
    touched_center: bool = False
    counted: bool = False
    last_seen_frame: int = 0


class GateCounter:
    """Contador direcional com duas fronteiras e maquina de estados por track.

    A passagem valida no sentido principal exige a sequencia estavel:
        RIGHT -> CENTER -> LEFT

    Isso reduz contagens por jitter da bounding box, viradas no lugar e pequenas
    oscilacoes proximas da antiga linha unica.
    """

    def __init__(
        self,
        left_x: float = 0.42,
        right_x: float = 0.58,
        stable_frames: int = 2,
        stale_after_frames: int = 120,
    ) -> None:
        if not 0 <= left_x < right_x <= 1:
            raise ValueError("Esperado 0 <= left_x < right_x <= 1")
        self.left_x = left_x
        self.right_x = right_x
        self.stable_frames = max(1, int(stable_frames))
        self.stale_after_frames = max(1, int(stale_after_frames))
        self.tracks: dict[int, TrackState] = {}
        self._lock = RLock()

    def reset(self) -> None:
        with self._lock:
            self.tracks.clear()

    def zone_for_x(self, x: float, frame_width: int) -> Zone:
        if frame_width <= 0:
            raise ValueError("frame_width deve ser > 0")
        xn = x / frame_width
        if xn <= self.left_x:
            return "LEFT"
        if xn >= self.right_x:
            return "RIGHT"
        return "CENTER"

    @staticmethod
    def bottom_center(bbox: tuple[float, float, float, float] | list[float]) -> tuple[float, float]:
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2.0, y2)

    def update(
        self,
        track_id: int,
        bbox: tuple[float, float, float, float] | list[float],
        frame_width: int,
        confidence: float,
        frame_index: int,
    ) -> dict | None:
        anchor_x, anchor_y = self.bottom_center(bbox)
        observed_zone = self.zone_for_x(anchor_x, frame_width)
        with self._lock:
            state = self.tracks.setdefault(track_id, TrackState())
            state.last_seen_frame = frame_index

            if state.candidate_zone == observed_zone:
                state.candidate_hits += 1
            else:
                state.candidate_zone = observed_zone
                state.candidate_hits = 1

            if state.candidate_hits < self.stable_frames:
                return None
            if state.stable_zone == observed_zone:
                return None

            previous = state.stable_zone
            state.stable_zone = observed_zone

            if previous is None:
                if observed_zone in ("LEFT", "RIGHT"):
                    state.origin_side = observed_zone
                return None

            # Entrou na zona central partindo de um lado conhecido.
            if observed_zone == "CENTER" and previous in ("LEFT", "RIGHT"):
                state.origin_side = previous
                state.touched_center = True
                return None

            # Voltou ao mesmo lado sem completar a travessia.
            if observed_zone in ("LEFT", "RIGHT") and observed_zone == state.origin_side:
                state.touched_center = False
                return None

            if not state.touched_center or state.origin_side not in ("LEFT", "RIGHT"):
                # Track pode ter nascido no centro. So arma quando estabilizar em um lado.
                if observed_zone in ("LEFT", "RIGHT"):
                    state.origin_side = observed_zone
                return None

            event = None

            if state.origin_side == "RIGHT" and observed_zone == "LEFT":
                if not state.counted:
                    state.counted = True
                    event = {
                        "track_id": track_id,
                        "direcao": "direita_para_esquerda",
                        "contabilizado": True,
                        "confidence": round(float(confidence), 4),
                        "anchor_x": round(anchor_x, 2),
                        "anchor_y": round(anchor_y, 2),
                        "frame_index": frame_index,
                    }
            elif state.origin_side == "LEFT" and observed_zone == "RIGHT":
                event = {
                    "track_id": track_id,
                    "direcao": "esquerda_para_direita",
                    "contabilizado": False,
                    "confidence": round(float(confidence), 4),
                    "anchor_x": round(anchor_x, 2),
                    "anchor_y": round(anchor_y, 2),
                    "frame_index": frame_index,
                }

            # Depois da travessia, o lado de chegada vira a nova origem.
            state.origin_side = observed_zone
            state.touched_center = False
            return event

    def cleanup(self, frame_index: int) -> None:
        with self._lock:
            stale = [
                track_id for track_id, state in self.tracks.items()
                if frame_index - state.last_seen_frame > self.stale_after_frames
            ]
            for track_id in stale:
                self.tracks.pop(track_id, None)
