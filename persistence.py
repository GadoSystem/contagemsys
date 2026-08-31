from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any


class EventDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    note TEXT
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    track_id INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    counted INTEGER NOT NULL,
                    confidence REAL,
                    frame_index INTEGER,
                    snapshot_path TEXT,
                    clip_path TEXT,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );

                CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, id DESC);
                CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC);
                """
            )

    def start_session(self, note: str | None = None) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE sessions SET ended_at = ? WHERE ended_at IS NULL", (now,))
            cur = conn.execute(
                "INSERT INTO sessions(started_at, note) VALUES (?, ?)",
                (now, note),
            )
            return int(cur.lastrowid)

    def insert_event(self, session_id: int, event: dict[str, Any]) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO events(
                    session_id, track_id, timestamp, direction, counted,
                    confidence, frame_index, snapshot_path, clip_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    int(event["track_id"]),
                    now,
                    str(event["direcao"]),
                    1 if event.get("contabilizado") else 0,
                    float(event.get("confidence", 0.0)),
                    int(event.get("frame_index", 0)),
                    event.get("snapshot_path"),
                    event.get("clip_path"),
                ),
            )
            return int(cur.lastrowid)

    def update_evidence(self, event_id: int, snapshot_path: str | None = None, clip_path: str | None = None) -> None:
        sets: list[str] = []
        values: list[Any] = []
        if snapshot_path is not None:
            sets.append("snapshot_path = ?")
            values.append(snapshot_path)
        if clip_path is not None:
            sets.append("clip_path = ?")
            values.append(clip_path)
        if not sets:
            return
        values.append(event_id)
        with self._lock, self._connect() as conn:
            conn.execute(f"UPDATE events SET {', '.join(sets)} WHERE id = ?", values)

    def get_event(self, event_id: int) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM events WHERE id = ?", (int(event_id),)).fetchone()
        return dict(row) if row else None

    def list_events(self, limit: int = 200, session_id: int | None = None) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 2000))
        with self._lock, self._connect() as conn:
            if session_id is None:
                rows = conn.execute(
                    "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM events WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                    (session_id, limit),
                ).fetchall()
        return [dict(row) for row in rows]

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY id DESC LIMIT ?", (max(1, min(limit, 500)),)
            ).fetchall()
        return [dict(row) for row in rows]
