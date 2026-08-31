from __future__ import annotations

import time
from threading import Event, Lock, Thread
from typing import Any

import cv2


class LatestFrameCamera:
    """Captura em thread separada mantendo somente o frame mais recente."""

    def __init__(self, source: Any = 0, width: int | None = None, height: int | None = None) -> None:
        self.source = source
        self.width = width
        self.height = height
        self.cap: cv2.VideoCapture | None = None
        self._frame = None
        self._frame_id = 0
        self._lock = Lock()
        self._stop = Event()
        self._thread: Thread | None = None
        self._fps = 0.0

    @property
    def fps(self) -> float:
        return self._fps

    def start(self) -> "LatestFrameCamera":
        source = int(self.source) if isinstance(self.source, str) and self.source.isdigit() else self.source
        self.cap = cv2.VideoCapture(source)
        if not self.cap.isOpened():
            raise RuntimeError(f"Nao foi possivel abrir a fonte de video: {self.source}")
        if self.width:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(self.width))
        if self.height:
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self.height))
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._stop.clear()
        self._thread = Thread(target=self._reader, name="camera-reader", daemon=True)
        self._thread.start()
        return self

    def _reader(self) -> None:
        frames = 0
        mark = time.perf_counter()
        while not self._stop.is_set() and self.cap is not None:
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            with self._lock:
                self._frame = frame
                self._frame_id += 1
            frames += 1
            now = time.perf_counter()
            dt = now - mark
            if dt >= 1.0:
                self._fps = frames / dt
                frames = 0
                mark = now

    def read(self) -> tuple[int, Any | None]:
        with self._lock:
            return self._frame_id, None if self._frame is None else self._frame.copy()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        if self.cap is not None:
            self.cap.release()
        self.cap = None
