from __future__ import annotations

from collections.abc import Callable

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from persistence import EventDatabase
from state import SharedState


def create_app(
    state: SharedState,
    db: EventDatabase,
    reset_callback: Callable[[], int],
) -> FastAPI:
    app = FastAPI(
        title="API de Contagem do Rebanho",
        version="3.0.0",
        description="API para consultar contagem, eventos, sessoes e metricas do sistema de visao computacional.",
    )

    @app.get("/health")
    def health() -> dict:
        snap = state.snapshot()
        return {"status": "ok", "sistema_rodando": snap["sistema_rodando"], "versao": "3.0.0"}

    @app.get("/contagem/atual")
    def current_count() -> dict:
        return state.snapshot()

    @app.get("/contagem/eventos")
    def events(limit: int = Query(default=100, ge=1, le=2000)) -> list[dict]:
        session_id = state.snapshot().get("session_id")
        return db.list_events(limit=limit, session_id=session_id)

    @app.get("/contagem/sessoes")
    def sessions(limit: int = Query(default=50, ge=1, le=500)) -> list[dict]:
        return db.list_sessions(limit=limit)

    @app.get("/contagem/eventos/{event_id}")
    def event_detail(event_id: int) -> dict:
        event = db.get_event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Evento nao encontrado")
        return event

    def _event_file(event_id: int, field: str) -> FileResponse:
        event = db.get_event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Evento nao encontrado")
        value = event.get(field)
        if not value:
            raise HTTPException(status_code=404, detail="Evidencia ainda nao disponivel")
        path = Path(value)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Arquivo de evidencia nao encontrado")
        return FileResponse(path)

    @app.get("/contagem/eventos/{event_id}/snapshot")
    def event_snapshot(event_id: int):
        return _event_file(event_id, "snapshot_path")

    @app.get("/contagem/eventos/{event_id}/clip")
    def event_clip(event_id: int):
        return _event_file(event_id, "clip_path")

    @app.post("/contagem/resetar")
    def reset() -> dict:
        new_session = reset_callback()
        return {"ok": True, "mensagem": "Nova sessao iniciada e contadores zerados.", "session_id": new_session}

    return app
