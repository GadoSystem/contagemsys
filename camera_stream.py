from __future__ import annotations

import os
import time
from threading import Event, Lock, Thread
from typing import Any

import cv2


class LatestFrameCamera:
    """Captura em thread separada mantendo somente o frame mais recente.

    Para webcams no Windows, tenta DirectShow primeiro e usa MJPG por padrao.
    Isso reduz bastante a largura de banda USB quando duas webcams estao ativas.
    """

    def __init__(
        self,
        source: Any = 0,
        width: int | None = None,
        height: int | None = None,
        fps: int | None = None,
        backend: str = "auto",
        fourcc: str | None = "MJPG",
    ) -> None:
        self.source = source
        self.width = width
        self.height = height
        self.requested_fps = fps
        self.backend = str(backend or "auto").lower()
        self.fourcc = str(fourcc or "").upper()
        self.cap: cv2.VideoCapture | None = None
        self._frame = None
        self._frame_id = 0
        self._lock = Lock()
        self._stop = Event()
        self._thread: Thread | None = None
        self._fps = 0.0
        self._actual_width = 0
        self._actual_height = 0
        self._actual_capture_fps = 0.0

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def actual_width(self) -> int:
        return self._actual_width

    @property
    def actual_height(self) -> int:
        return self._actual_height

    @property
    def actual_capture_fps(self) -> float:
        return self._actual_capture_fps

    def _open_candidates(self, source: Any) -> list[tuple[str, int | None]]:
        if not isinstance(source, int):
            return [("default", None)]

        if self.backend == "dshow":
            return [("dshow", cv2.CAP_DSHOW), ("default", None)]
        if self.backend == "msmf":
            return [("msmf", cv2.CAP_MSMF), ("default", None)]
        if self.backend == "default":
            return [("default", None)]

        # auto: no Windows, DirectShow costuma ter menor latencia para webcams USB.
        if os.name == "nt":
            return [
                ("dshow", cv2.CAP_DSHOW),
                ("msmf", cv2.CAP_MSMF),
                ("default", None),
            ]
        return [("default", None)]

    def _configure_capture(self, cap: cv2.VideoCapture) -> None:
        # MJPG reduz o trafego USB de duas webcams quando o dispositivo suporta.
        if self.fourcc and len(self.fourcc) == 4:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*self.fourcc))
        if self.width:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(self.width))
        if self.height:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self.height))
        if self.requested_fps:
            cap.set(cv2.CAP_PROP_FPS, int(self.requested_fps))
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def start(self) -> "LatestFrameCamera":
        source = int(self.source) if isinstance(self.source, str) and self.source.isdigit() else self.source
        errors: list[str] = []

        for backend_name, backend_code in self._open_candidates(source):
            cap = (
                cv2.VideoCapture(source, backend_code)
                if backend_code is not None
                else cv2.VideoCapture(source)
            )
            if not cap.isOpened():
                errors.append(backend_name)
                cap.release()
                continue

            self._configure_capture(cap)
            ok, frame = cap.read()
            if not ok or frame is None:
                errors.append(f"{backend_name}:sem-frame")
                cap.release()
                continue

            self.cap = cap
            with self._lock:
                self._frame = frame
                self._frame_id = 1
            break

        if self.cap is None:
            attempted = ", ".join(errors) if errors else "backend padrao"
            raise RuntimeError(
                f"Nao foi possivel abrir a fonte de video: {self.source}. Tentativas: {attempted}"
            )

        self._actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        self._actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        self._actual_capture_fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 0.0)

        self._stop.clear()
        self._thread = Thread(target=self._reader, name=f"camera-reader-{self.source}", daemon=True)
        self._thread.start()
        return self

    def _reader(self) -> None:
        frames = 0
        mark = time.perf_counter()
        while not self._stop.is_set() and self.cap is not None:
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.005)
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

    def read(self, *, copy: bool = True) -> tuple[int, Any | None]:
        with self._lock:
            if self._frame is None:
                return self._frame_id, None
            return self._frame_id, self._frame.copy() if copy else self._frame

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        if self.cap is not None:
            self.cap.release()
        self.cap = None
