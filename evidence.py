from __future__ import annotations

import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Callable

import cv2


class EvidenceRecorder:
    """Mantem pequeno buffer em RAM e salva snapshot/clip somente em eventos."""

    def __init__(
        self,
        directory: str | Path,
        enabled: bool = True,
        save_snapshot: bool = True,
        save_clip: bool = True,
        pre_seconds: float = 3.0,
        post_seconds: float = 3.0,
        clip_fps: float = 20.0,
        on_clip_ready: Callable[[int, str], None] | None = None,
    ) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.enabled = enabled
        self.save_snapshot = save_snapshot
        self.save_clip = save_clip
        self.pre_seconds = max(0.0, pre_seconds)
        self.post_seconds = max(0.0, post_seconds)
        self.clip_fps = max(1.0, clip_fps)
        self.on_clip_ready = on_clip_ready
        self._buffer: deque[tuple[float, object]] = deque()
        self._pending: dict[int, dict] = {}
        self._lock = Lock()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="evidence-writer")
        self._last_sample = 0.0

    def push(self, frame) -> None:
        if not self.enabled:
            return
        now = time.monotonic()
        # Amostra no FPS do clip para evitar manter dezenas/centenas de MB desnecessarios em RAM.
        if now - self._last_sample < (1.0 / self.clip_fps):
            return
        self._last_sample = now
        with self._lock:
            self._buffer.append((now, frame.copy()))
            cutoff = now - self.pre_seconds
            while self._buffer and self._buffer[0][0] < cutoff:
                self._buffer.popleft()

            done: list[int] = []
            for event_id, pending in self._pending.items():
                pending["frames"].append(frame.copy())
                if now >= pending["deadline"]:
                    done.append(event_id)

            for event_id in done:
                pending = self._pending.pop(event_id)
                self._pool.submit(self._write_clip, event_id, pending["path"], pending["frames"])

    def start_event(self, event_id: int, frame, label: str) -> tuple[str | None, str | None]:
        if not self.enabled:
            return None, None
        stamp = datetime.now().strftime("%Y-%m-%d")
        day_dir = self.directory / stamp
        day_dir.mkdir(parents=True, exist_ok=True)
        base = f"evento_{event_id:06d}_{label}_{datetime.now().strftime('%H%M%S')}"

        snapshot_path: str | None = None
        clip_path: str | None = None
        if self.save_snapshot:
            snap = day_dir / f"{base}.jpg"
            cv2.imwrite(str(snap), frame)
            snapshot_path = str(snap)

        if self.save_clip:
            clip = day_dir / f"{base}.mp4"
            clip_path = str(clip)
            with self._lock:
                frames = [buf_frame.copy() for _, buf_frame in self._buffer]
                frames.append(frame.copy())
                self._pending[event_id] = {
                    "path": clip,
                    "frames": frames,
                    "deadline": time.monotonic() + self.post_seconds,
                }
        return snapshot_path, clip_path

    def _write_clip(self, event_id: int, path: Path, frames: list) -> None:
        if not frames:
            return
        h, w = frames[0].shape[:2]
        writer = cv2.VideoWriter(
            str(path), cv2.VideoWriter_fourcc(*"mp4v"), self.clip_fps, (w, h)
        )
        if not writer.isOpened():
            return
        try:
            for frame in frames:
                if frame.shape[1] != w or frame.shape[0] != h:
                    frame = cv2.resize(frame, (w, h))
                writer.write(frame)
        finally:
            writer.release()
        if self.on_clip_ready:
            self.on_clip_ready(event_id, str(path))

    def close(self) -> None:
        # Se o programa for encerrado logo apos um evento, salva o trecho parcial disponivel.
        with self._lock:
            pending = list(self._pending.items())
            self._pending.clear()
        for event_id, item in pending:
            self._pool.submit(self._write_clip, event_id, item["path"], item["frames"])
        self._pool.shutdown(wait=True, cancel_futures=False)
