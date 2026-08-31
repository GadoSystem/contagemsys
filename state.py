from __future__ import annotations

from collections import deque
from threading import RLock
from typing import Any


class SharedState:
    def __init__(self, max_events: int = 200) -> None:
        self._lock = RLock()
        self._max_events = max_events
        self._events: deque[dict[str, Any]] = deque(maxlen=max_events)
        self._data: dict[str, Any] = {
            "total_contado": 0,
            "animais_no_frame_agora": 0,
            "retornos_esquerda_para_direita": 0,
            "direcao_contada": "direita_para_esquerda",
            "fps_ia": 0.0,
            "fps_camera": 0.0,
            "latencia_ia_ms": 0.0,
            "sistema_rodando": False,
            "session_id": None,
            "tracker": None,
            "modelo": None,
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def update_metrics(self, **kwargs: Any) -> None:
        with self._lock:
            self._data.update(kwargs)

    def register_event(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._events.appendleft(dict(event))
            if event.get("contabilizado"):
                self._data["total_contado"] += 1
            elif event.get("direcao") == "esquerda_para_direita":
                self._data["retornos_esquerda_para_direita"] += 1

    def events(self, limit: int | None = None) -> list[dict[str, Any]]:
        with self._lock:
            values = list(self._events)
        return values[:limit] if limit else values

    def reset_counters(self, session_id: int | None = None) -> None:
        with self._lock:
            self._data["total_contado"] = 0
            self._data["animais_no_frame_agora"] = 0
            self._data["retornos_esquerda_para_direita"] = 0
            self._data["session_id"] = session_id
            self._events.clear()
