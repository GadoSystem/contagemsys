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

    @staticmethod
    def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {str(row[1]) for row in rows}

    def _ensure_column(
        self,
        conn: sqlite3.Connection,
        table: str,
        column: str,
        declaration: str,
    ) -> None:
        if column not in self._columns(conn, table):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT NOT NULL DEFAULT 'legacy',
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    note TEXT
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    camera_id TEXT NOT NULL DEFAULT 'legacy',
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

                CREATE TABLE IF NOT EXISTS camera_owners (
                    camera_id TEXT PRIMARY KEY,
                    usuario_id INTEGER NOT NULL,
                    usuario_nome TEXT NOT NULL,
                    usuario_email TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )

            # Migra automaticamente bancos V3 sem apagar dados.
            self._ensure_column(conn, "sessions", "camera_id", "TEXT NOT NULL DEFAULT 'legacy'")
            self._ensure_column(conn, "events", "camera_id", "TEXT NOT NULL DEFAULT 'legacy'")

            conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_camera
                    ON sessions(camera_id, id DESC);
                CREATE INDEX IF NOT EXISTS idx_events_session
                    ON events(session_id, id DESC);
                CREATE INDEX IF NOT EXISTS idx_events_camera
                    ON events(camera_id, id DESC);
                CREATE INDEX IF NOT EXISTS idx_events_timestamp
                    ON events(timestamp DESC);
                """
            )

    def start_session(self, camera_id: str, note: str | None = None) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET ended_at = ? WHERE ended_at IS NULL AND camera_id = ?",
                (now, camera_id),
            )
            cur = conn.execute(
                "INSERT INTO sessions(camera_id, started_at, note) VALUES (?, ?, ?)",
                (camera_id, now, note),
            )
            return int(cur.lastrowid)

    def insert_event(self, session_id: int, camera_id: str, event: dict[str, Any]) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO events(
                    session_id, camera_id, track_id, timestamp, direction, counted,
                    confidence, frame_index, snapshot_path, clip_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    camera_id,
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

    def update_evidence(
        self,
        event_id: int,
        snapshot_path: str | None = None,
        clip_path: str | None = None,
    ) -> None:
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

    def list_events(
        self,
        limit: int = 200,
        session_id: int | None = None,
        camera_id: str | None = None,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 2000))
        clauses: list[str] = []
        values: list[Any] = []
        if session_id is not None:
            clauses.append("session_id = ?")
            values.append(int(session_id))
        if camera_id is not None:
            clauses.append("camera_id = ?")
            values.append(camera_id)

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(limit)
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM events{where} ORDER BY id DESC LIMIT ?",
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def list_sessions(self, limit: int = 50, camera_id: str | None = None) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        with self._lock, self._connect() as conn:
            if camera_id is None:
                rows = conn.execute(
                    "SELECT * FROM sessions ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM sessions WHERE camera_id = ? ORDER BY id DESC LIMIT ?",
                    (camera_id, limit),
                ).fetchall()
        return [dict(row) for row in rows]


    def set_camera_owner(
        self,
        camera_id: str,
        usuario_id: int,
        usuario_nome: str,
        usuario_email: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO camera_owners(camera_id, usuario_id, usuario_nome, usuario_email, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(camera_id) DO UPDATE SET
                    usuario_id = excluded.usuario_id,
                    usuario_nome = excluded.usuario_nome,
                    usuario_email = excluded.usuario_email,
                    updated_at = excluded.updated_at
                """,
                (camera_id, int(usuario_id), usuario_nome, usuario_email, now),
            )

    def remove_camera_owner(self, camera_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM camera_owners WHERE camera_id = ?", (camera_id,))

    def get_camera_owner(self, camera_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM camera_owners WHERE camera_id = ?",
                (camera_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_camera_owners(self, usuario_id: int | None = None) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            if usuario_id is None:
                rows = conn.execute(
                    "SELECT * FROM camera_owners ORDER BY camera_id"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM camera_owners WHERE usuario_id = ? ORDER BY camera_id",
                    (int(usuario_id),),
                ).fetchall()
        return [dict(row) for row in rows]
