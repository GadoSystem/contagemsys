"""Lógica de contagem direcional independente do detector/tracker.

A regra principal é simples: IDs do tracker NÃO são a contagem.
Um objeto só entra no total quando sua trajetória cruza a linha no sentido
DIREITA -> ESQUERDA. Cruzamentos no sentido inverso são tratados como retorno
e bloqueiam uma futura recontagem do mesmo ID.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Iterable, List, Optional, Tuple


LEFT = -1
NEUTRAL = 0
RIGHT = 1


@dataclass
class TrackState:
    track_id: int
    first_seen_frame: int
    last_seen_frame: int
    frames_seen: int = 0
    stable_side: int = NEUTRAL
    counted: bool = False
    blocked_as_return: bool = False
    leftmost_x: float = float("inf")
    rightmost_x: float = float("-inf")
    trail: Deque[Tuple[int, int]] = field(default_factory=lambda: deque(maxlen=30))


@dataclass
class CrossingEvent:
    track_id: int
    direction: str
    counted: bool
    frame_index: int
    point: Tuple[int, int]


class DirectionalLineCounter:
    """Conta cruzamentos robustos em uma linha vertical.

    Histerese: existe uma faixa morta ao redor da linha. O objeto precisa estar
    claramente de um lado e depois claramente do outro lado para gerar evento.
    Isso evita contagem por tremedeira da caixa, giro do corpo e ruído do detector.
    """

    def __init__(
        self,
        line_x: int,
        frame_width: int,
        dead_zone_px: int = 18,
        min_track_frames: int = 3,
        min_displacement_px: int = 36,
        max_track_age_frames: int = 120,
    ) -> None:
        self.line_x = int(line_x)
        self.frame_width = int(frame_width)
        self.dead_zone_px = max(2, int(dead_zone_px))
        self.min_track_frames = max(2, int(min_track_frames))
        self.min_displacement_px = max(self.dead_zone_px * 2, int(min_displacement_px))
        self.max_track_age_frames = max(30, int(max_track_age_frames))

        self.total_counted = 0
        self.reverse_crossings = 0
        self._tracks: Dict[int, TrackState] = {}
        self._counted_ids: set[int] = set()
        self._blocked_ids: set[int] = set()

    def reset(self) -> None:
        self.total_counted = 0
        self.reverse_crossings = 0
        self._tracks.clear()
        self._counted_ids.clear()
        self._blocked_ids.clear()

    def _side(self, x: float) -> int:
        if x < self.line_x - self.dead_zone_px:
            return LEFT
        if x > self.line_x + self.dead_zone_px:
            return RIGHT
        return NEUTRAL

    def update(
        self,
        track_id: int,
        point: Tuple[int, int],
        frame_index: int,
    ) -> Optional[CrossingEvent]:
        x, y = point
        state = self._tracks.get(track_id)
        if state is None:
            state = TrackState(
                track_id=track_id,
                first_seen_frame=frame_index,
                last_seen_frame=frame_index,
                counted=track_id in self._counted_ids,
                blocked_as_return=track_id in self._blocked_ids,
            )
            self._tracks[track_id] = state

        state.frames_seen += 1
        state.last_seen_frame = frame_index
        state.leftmost_x = min(state.leftmost_x, x)
        state.rightmost_x = max(state.rightmost_x, x)
        state.trail.append((int(x), int(y)))

        side = self._side(x)
        if side == NEUTRAL:
            return None

        if state.stable_side == NEUTRAL:
            state.stable_side = side
            return None

        if side == state.stable_side:
            return None

        previous_side = state.stable_side
        state.stable_side = side

        displacement = state.rightmost_x - state.leftmost_x
        valid_trajectory = (
            state.frames_seen >= self.min_track_frames
            and displacement >= self.min_displacement_px
        )
        if not valid_trajectory:
            return None

        # Sentido principal: DIREITA -> ESQUERDA.
        if previous_side == RIGHT and side == LEFT:
            if state.counted or state.blocked_as_return:
                return CrossingEvent(
                    track_id=track_id,
                    direction="direita_para_esquerda",
                    counted=False,
                    frame_index=frame_index,
                    point=(int(x), int(y)),
                )

            state.counted = True
            self._counted_ids.add(track_id)
            self.total_counted += 1
            return CrossingEvent(
                track_id=track_id,
                direction="direita_para_esquerda",
                counted=True,
                frame_index=frame_index,
                point=(int(x), int(y)),
            )

        # Sentido inverso: interpretado como retorno de algo que já passou.
        if previous_side == LEFT and side == RIGHT:
            if not state.blocked_as_return:
                self.reverse_crossings += 1
            state.blocked_as_return = True
            self._blocked_ids.add(track_id)
            return CrossingEvent(
                track_id=track_id,
                direction="esquerda_para_direita",
                counted=False,
                frame_index=frame_index,
                point=(int(x), int(y)),
            )

        return None

    def cleanup(self, current_frame: int) -> None:
        expired = [
            track_id
            for track_id, state in self._tracks.items()
            if current_frame - state.last_seen_frame > self.max_track_age_frames
        ]
        for track_id in expired:
            del self._tracks[track_id]

    def update_many(
        self,
        tracks: Iterable[Tuple[int, Tuple[int, int]]],
        frame_index: int,
    ) -> List[CrossingEvent]:
        events: List[CrossingEvent] = []
        for track_id, point in tracks:
            event = self.update(track_id, point, frame_index)
            if event is not None:
                events.append(event)
        self.cleanup(frame_index)
        return events

    def trail_for(self, track_id: int) -> List[Tuple[int, int]]:
        state = self._tracks.get(track_id)
        return [] if state is None else list(state.trail)

    def status_for(self, track_id: int) -> str:
        state = self._tracks.get(track_id)
        if state is None:
            return "tracking"
        if state.counted:
            return "contado"
        if state.blocked_as_return:
            return "retorno"
        return "tracking"
