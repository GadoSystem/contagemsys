from __future__ import annotations

import asyncio
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Security
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.security import APIKeyHeader

from persistence import EventDatabase
from state import LiveFrameStore, SharedState


CameraApiContext = dict[str, Any]


def create_app(
    cameras: dict[str, CameraApiContext],
    db: EventDatabase,
    reset_all_callback: Callable[[], dict[str, int]],
    *,
    api_key: str | None,
    auth_enabled: bool = True,
    stream_fps: int = 10,
) -> FastAPI:
    app = FastAPI(
        title="API de Contagem do Rebanho",
        version="4.1.0",
        description=(
            "API autenticada para consultar multiplas cameras, contagem, eventos, sessoes "
            "e imagens em tempo real do sistema de visao computacional."
        ),
    )

    api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

    def require_api_key(received: str | None = Security(api_key_header)) -> None:
        if not auth_enabled:
            return
        if not api_key:
            raise HTTPException(status_code=503, detail="Autenticacao da API nao configurada")
        if not received or not secrets.compare_digest(received, api_key):
            raise HTTPException(status_code=401, detail="API key invalida ou ausente")

    protected = APIRouter(dependencies=[Depends(require_api_key)])

    def get_camera(camera_id: str) -> CameraApiContext:
        camera = cameras.get(camera_id)
        if camera is None:
            raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' nao encontrada")
        return camera

    @protected.get("/health")
    def health() -> dict:
        snapshots = [ctx["state"].snapshot() for ctx in cameras.values()]
        running = sum(1 for snap in snapshots if snap["sistema_rodando"])
        return {
            "status": "ok" if running else "degraded",
            "versao": "4.1.0",
            "cameras_configuradas": len(snapshots),
            "cameras_rodando": running,
        }

    @protected.get("/cameras")
    def list_cameras() -> list[dict]:
        result: list[dict] = []
        for camera_id, ctx in cameras.items():
            snap = ctx["state"].snapshot()
            result.append(
                {
                    "id": camera_id,
                    "name": snap["camera_name"],
                    "status": "online" if snap["sistema_rodando"] else "offline",
                    "total_contado": snap["total_contado"],
                    "animais_no_frame_agora": snap["animais_no_frame_agora"],
                    "retornos_esquerda_para_direita": snap["retornos_esquerda_para_direita"],
                    "fps_camera": snap["fps_camera"],
                    "fps_ia": snap["fps_ia"],
                    "latencia_ia_ms": snap["latencia_ia_ms"],
                    "espera_fila_ia_ms": snap.get("espera_fila_ia_ms", 0.0),
                    "fps_ia_alvo": snap.get("fps_ia_alvo"),
                    "resolucao_camera": snap.get("resolucao_camera"),
                    "session_id": snap["session_id"],
                    "ultimo_erro": snap.get("ultimo_erro"),
                    "frame_url": f"/cameras/{camera_id}/frame.jpg",
                    "stream_url": f"/cameras/{camera_id}/stream.mjpg",
                }
            )
        return result

    @protected.get("/contagem/atual")
    def aggregate_count() -> dict:
        snaps = [ctx["state"].snapshot() for ctx in cameras.values()]
        return {
            "total_contado": sum(int(s["total_contado"]) for s in snaps),
            "animais_no_frame_agora": sum(int(s["animais_no_frame_agora"]) for s in snaps),
            "retornos_esquerda_para_direita": sum(
                int(s["retornos_esquerda_para_direita"]) for s in snaps
            ),
            "cameras_online": sum(1 for s in snaps if s["sistema_rodando"]),
            "cameras_total": len(snaps),
            "cameras": snaps,
        }

    @protected.get("/cameras/{camera_id}/contagem/atual")
    def current_count(camera_id: str) -> dict:
        return get_camera(camera_id)["state"].snapshot()

    @protected.get("/contagem/eventos")
    def events(
        limit: int = Query(default=100, ge=1, le=2000),
        camera_id: str | None = Query(default=None),
    ) -> list[dict]:
        if camera_id is not None:
            get_camera(camera_id)
        return db.list_events(limit=limit, camera_id=camera_id)

    @protected.get("/cameras/{camera_id}/contagem/eventos")
    def camera_events(camera_id: str, limit: int = Query(default=100, ge=1, le=2000)) -> list[dict]:
        get_camera(camera_id)
        return db.list_events(limit=limit, camera_id=camera_id)

    @protected.get("/contagem/sessoes")
    def sessions(
        limit: int = Query(default=50, ge=1, le=500),
        camera_id: str | None = Query(default=None),
    ) -> list[dict]:
        if camera_id is not None:
            get_camera(camera_id)
        return db.list_sessions(limit=limit, camera_id=camera_id)

    @protected.get("/cameras/{camera_id}/contagem/sessoes")
    def camera_sessions(camera_id: str, limit: int = Query(default=50, ge=1, le=500)) -> list[dict]:
        get_camera(camera_id)
        return db.list_sessions(limit=limit, camera_id=camera_id)

    @protected.get("/contagem/eventos/{event_id}")
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

    @protected.get("/contagem/eventos/{event_id}/snapshot")
    def event_snapshot(event_id: int):
        return _event_file(event_id, "snapshot_path")

    @protected.get("/contagem/eventos/{event_id}/clip")
    def event_clip(event_id: int):
        return _event_file(event_id, "clip_path")

    @protected.post("/contagem/resetar")
    def reset_all() -> dict:
        sessions = reset_all_callback()
        return {
            "ok": True,
            "mensagem": "Todas as cameras foram reiniciadas e receberam novas sessoes.",
            "sessions": sessions,
        }

    @protected.post("/cameras/{camera_id}/contagem/resetar")
    def reset_camera(camera_id: str) -> dict:
        camera = get_camera(camera_id)
        new_session = camera["reset"]()
        return {
            "ok": True,
            "camera_id": camera_id,
            "session_id": new_session,
            "mensagem": "Contadores da camera zerados.",
        }

    @protected.get("/cameras/{camera_id}/frame.jpg")
    def camera_frame(camera_id: str) -> Response:
        camera = get_camera(camera_id)
        frame_store: LiveFrameStore = camera["frames"]
        _, jpeg = frame_store.jpeg()
        if jpeg is None:
            raise HTTPException(status_code=503, detail="Frame ainda nao disponivel")
        return Response(
            content=jpeg,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )

    @protected.get("/cameras/{camera_id}/stream.mjpg")
    async def camera_stream(camera_id: str) -> StreamingResponse:
        camera = get_camera(camera_id)
        frame_store: LiveFrameStore = camera["frames"]
        delay = 1.0 / max(1, min(int(stream_fps), 30))

        async def generate():
            last_version = -1
            while True:
                version, jpeg = frame_store.jpeg()
                if jpeg is not None and version != last_version:
                    last_version = version
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        + f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii")
                        + jpeg
                        + b"\r\n"
                    )
                await asyncio.sleep(delay)

        return StreamingResponse(
            generate(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )

    app.include_router(protected)
    return app
