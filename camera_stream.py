from __future__ import annotations

import os
from urllib.parse import quote, urlsplit, urlunsplit
import time
from threading import Event, Lock, Thread
from typing import Any

import cv2


def resolve_video_source(source: Any, username_env: str | None = None,
                         password_env: str | None = None) -> Any:
    """Expande URL por variaveis de ambiente; credenciais ficam fora do YAML."""
    if not isinstance(source, str):
        return source
    value = os.path.expandvars(source)
    if value.isdigit():
        return int(value)
    if username_env or password_env:
        user = os.getenv(str(username_env), "") if username_env else ""
        password = os.getenv(str(password_env), "") if password_env else ""
        if user:
            parsed = urlsplit(value)
            if parsed.scheme in ("rtsp", "rtsps", "http", "https") and parsed.hostname:
                host = parsed.hostname
                if ":" in host:
                    host = f"[{host}]"
                netloc = f"{quote(user, safe='')}:{quote(password, safe='')}@{host}"
                if parsed.port:
                    netloc += f":{parsed.port}"
                return urlunsplit(parsed._replace(netloc=netloc))
    return value


def open_video_source(source: Any, *, backend: str = "auto", width: int | None = None,
                      height: int | None = None, fps: int | None = None,
                      fourcc: str = "MJPG", open_timeout_ms: int = 2500,
                      read_timeout_ms: int = 2500):
    """Abre webcam / RTSP / HTTP. Falha retorna None, nunca reutiliza frames."""
    is_index = isinstance(source, int)
    backend = str(backend).lower()
    codes = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF,
             "ffmpeg": cv2.CAP_FFMPEG, "gstreamer": cv2.CAP_GSTREAMER}
    code = codes.get(backend)
    if not is_index and backend in ("auto", "default", "dshow", "msmf"):
        code = cv2.CAP_FFMPEG
    if code is not None and not is_index:
        try:
            cap = cv2.VideoCapture(source, code, [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(open_timeout_ms),
                cv2.CAP_PROP_READ_TIMEOUT_MSEC, int(read_timeout_ms),
            ])
        except (TypeError, cv2.error):
            cap = cv2.VideoCapture(source, code)
    else:
        cap = cv2.VideoCapture(source, code) if code is not None else cv2.VideoCapture(source)
    if not cap.isOpened():
        cap.release()
        return None
    if is_index:
        # Seleciona o formato comprimido ANTES de negociar a resolucao/FPS.
        # Em diversos drivers UVC, MJPG evita saturacao do barramento com 2 USB.
        if fourcc and len(fourcc) == 4:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
        if width:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(width))
        if height:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(height))
        if fps:
            cap.set(cv2.CAP_PROP_FPS, int(fps))
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


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
        username_env: str | None = None,
        password_env: str | None = None,
    ) -> None:
        self.source = source
        self.username_env = username_env
        self.password_env = password_env
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
        self._last_frame_at = 0.0
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

    def frame_age_seconds(self) -> float:
        """Idade do ultimo frame entregue pelo dispositivo, nao do frame renderizado."""
        with self._lock:
            instante = self._last_frame_at
        return time.monotonic() - instante if instante else float("inf")

    def healthy(self, max_age_seconds: float = 3.0) -> bool:
        return self.frame_age_seconds() < max_age_seconds

    def _open_candidates(self, source: Any) -> list[tuple[str, int | None]]:
        if not isinstance(source, int):
            return [("default", None)]

        # Backend escolhido explicitamente nao cai para outro: DirectShow e Media
        # Foundation numeram as webcams em ordens diferentes, entao o indice 1 de um
        # pode ser a mesma camera fisica que o indice 0 do outro (duas cameras
        # mostrando a mesma imagem). Melhor falhar com erro claro.
        if self.backend == "dshow":
            return [("dshow", cv2.CAP_DSHOW)]
        if self.backend == "msmf":
            return [("msmf", cv2.CAP_MSMF)]
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
        if self.fourcc and len(self.fourcc) == 4:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*self.fourcc))
        if self.width:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(self.width))
        if self.height:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self.height))
        if self.requested_fps:
            cap.set(cv2.CAP_PROP_FPS, int(self.requested_fps))
        # MJPG reduz o trafego USB de duas webcams quando o dispositivo suporta.
        # No DirectShow o FOURCC so vale se vier DEPOIS da resolucao: antes, a
        # troca de resolucao volta a camera para YUY2 (sem compressao, ~18 MB/s).
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def start(self) -> "LatestFrameCamera":
        source = resolve_video_source(self.source, self.username_env, self.password_env)
        errors: list[str] = []

        for backend_name, backend_code in self._open_candidates(source):
            cap = open_video_source(
                source, backend=backend_name, width=self.width, height=self.height,
                fps=self.requested_fps, fourcc=self.fourcc,
            )
            if cap is None:
                errors.append(backend_name)
                continue
            ok, frame = cap.read()
            if not ok or frame is None:
                errors.append(f"{backend_name}:sem-frame")
                cap.release()
                continue

            self.cap = cap
            with self._lock:
                self._frame = frame
                self._frame_id = 1
                self._last_frame_at = time.monotonic()
            break

        if self.cap is None:
            attempted = ", ".join(errors) if errors else "backend padrao"
            # Nao incluir senha de RTSP/HTTP em logs.
            origem = f"indice {source}" if isinstance(source, int) else "stream de rede"
            raise RuntimeError(
                f"Nao foi possivel abrir a fonte ({origem}). Tentativas: {attempted}"
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
            if not ok or frame is None:
                if self.frame_age_seconds() >= 1.5:
                    self._fps = 0.0
                self._stop.wait(0.05)
                continue
            with self._lock:
                self._frame = frame
                self._frame_id += 1
                self._last_frame_at = time.monotonic()
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
        if self._thread and self._thread.is_alive():
            # Aguarda liberar a captura anterior ANTES de tentar reconectar.
            self._thread.join(timeout=1.0)
