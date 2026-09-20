from __future__ import annotations

import asyncio
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Security
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from auth import AuthService, AuthenticationError, IntegrationError
from persistence import EventDatabase
from state import LiveFrameStore
from web_ui import ADMIN_HTML, LOGIN_HTML, PANEL_HTML


CameraApiContext = dict[str, Any]


class LoginRequest(BaseModel):
    login: str
    senha: str


class AdminLoginRequest(BaseModel):
    usuario: str
    senha: str


class CameraOwnerRequest(BaseModel):
    usuario_id: int
    nome: str
    email: str | None = None


def create_app(
    cameras: dict[str, CameraApiContext],
    db: EventDatabase,
    reset_all_callback: Callable[[], dict[str, int]],
    *,
    auth_service: AuthService,
    integration_key: str,
    stream_fps: int = 10,
) -> FastAPI:
    app = FastAPI(
        title="ContagemSys - API Web",
        version="5.0.0",
        description=(
            "Contagem multi-camera com login pelo Rebano, vinculo manual camera/usuario "
            "e integracao segura com o backend do Rebano."
        ),
    )

    bearer = HTTPBearer(auto_error=False)

    def _decode_token(credentials: HTTPAuthorizationCredentials | None) -> dict[str, Any]:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Token ausente")
        try:
            return auth_service.decode_token(credentials.credentials)
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    def require_user(
        credentials: HTTPAuthorizationCredentials | None = Security(bearer),
    ) -> dict[str, Any]:
        payload = _decode_token(credentials)
        if payload.get("role") != "user":
            raise HTTPException(status_code=403, detail="Acesso de usuario necessario")
        try:
            payload["usuario_id"] = int(payload["sub"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=401, detail="Token sem usuario valido") from exc
        return payload

    def require_admin(
        credentials: HTTPAuthorizationCredentials | None = Security(bearer),
    ) -> dict[str, Any]:
        payload = _decode_token(credentials)
        if payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Acesso de administrador necessario")
        return payload

    def require_integration_key(
        received: str | None = Header(default=None, alias="X-Integration-Key"),
    ) -> None:
        if not received or not secrets.compare_digest(received, integration_key):
            raise HTTPException(status_code=401, detail="Chave de integracao invalida")

    def get_camera(camera_id: str) -> CameraApiContext:
        camera = cameras.get(camera_id)
        if camera is None:
            raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' nao encontrada")
        return camera

    def require_owner(camera_id: str, usuario_id: int) -> CameraApiContext:
        camera = get_camera(camera_id)
        owner = db.get_camera_owner(camera_id)
        if owner is None or int(owner["usuario_id"]) != int(usuario_id):
            raise HTTPException(status_code=404, detail="Camera nao encontrada para este usuario")
        return camera

    def camera_summary(camera_id: str, ctx: CameraApiContext) -> dict[str, Any]:
        snap = ctx["state"].snapshot()
        owner = db.get_camera_owner(camera_id)
        return {
            "id": camera_id,
            "name": snap["camera_name"],
            "status": "online" if snap["sistema_rodando"] else "offline",
            "total_contado": snap["total_contado"],
            "animais_no_frame_agora": snap["animais_no_frame_agora"],
            "retornos_esquerda_para_direita": snap["retornos_esquerda_para_direita"],
            "fps_camera": snap["fps_camera"],
            "fps_ia": snap["fps_ia"],
            "latencia_ia_ms": snap["latencia_ia_ms"],
            "session_id": snap["session_id"],
            "ultimo_erro": snap.get("ultimo_erro"),
            "usuario_id": int(owner["usuario_id"]) if owner else None,
            "usuario_nome": owner["usuario_nome"] if owner else None,
            "usuario_email": owner["usuario_email"] if owner else None,
        }

    def cameras_for_user(usuario_id: int) -> list[dict[str, Any]]:
        owned = {row["camera_id"] for row in db.list_camera_owners(usuario_id=usuario_id)}
        return [
            camera_summary(camera_id, ctx)
            for camera_id, ctx in cameras.items()
            if camera_id in owned
        ]

    def jpeg_response(camera: CameraApiContext) -> Response:
        frame_store: LiveFrameStore = camera["frames"]
        _, jpeg = frame_store.jpeg()
        if jpeg is None:
            raise HTTPException(status_code=503, detail="Frame ainda nao disponivel")
        return Response(
            content=jpeg,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )

    def mjpeg_response(camera: CameraApiContext) -> StreamingResponse:
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

    # -------------------- Interface web --------------------

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def login_page() -> str:
        return LOGIN_HTML

    @app.get("/painel", response_class=HTMLResponse, include_in_schema=False)
    def panel_page() -> str:
        return PANEL_HTML

    @app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
    def admin_page() -> str:
        return ADMIN_HTML

    # -------------------- Autenticacao --------------------

    @app.post("/api/auth/login")
    async def user_login(body: LoginRequest) -> dict[str, Any]:
        try:
            return await auth_service.login_user(body.login, body.senha)
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except IntegrationError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/api/auth/admin/login")
    def admin_login(body: AdminLoginRequest) -> dict[str, Any]:
        try:
            return auth_service.login_admin(body.usuario, body.senha)
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    # -------------------- Usuario logado --------------------

    @app.get("/api/minhas-cameras")
    def my_cameras(user: dict[str, Any] = Depends(require_user)) -> list[dict[str, Any]]:
        return cameras_for_user(user["usuario_id"])

    @app.get("/api/minhas-cameras/{camera_id}/contagem")
    def my_camera_count(
        camera_id: str,
        user: dict[str, Any] = Depends(require_user),
    ) -> dict[str, Any]:
        camera = require_owner(camera_id, user["usuario_id"])
        return camera["state"].snapshot()

    @app.get("/api/minhas-cameras/{camera_id}/frame.jpg")
    def my_camera_frame(
        camera_id: str,
        user: dict[str, Any] = Depends(require_user),
    ) -> Response:
        return jpeg_response(require_owner(camera_id, user["usuario_id"]))

    @app.get("/api/minhas-cameras/{camera_id}/stream.mjpg")
    def my_camera_stream(
        camera_id: str,
        user: dict[str, Any] = Depends(require_user),
    ) -> StreamingResponse:
        return mjpeg_response(require_owner(camera_id, user["usuario_id"]))

    @app.get("/api/minhas-cameras/{camera_id}/eventos")
    def my_camera_events(
        camera_id: str,
        limit: int = Query(default=100, ge=1, le=1000),
        user: dict[str, Any] = Depends(require_user),
    ) -> list[dict[str, Any]]:
        require_owner(camera_id, user["usuario_id"])
        return db.list_events(limit=limit, camera_id=camera_id)

    # -------------------- Administracao dos vinculos --------------------

    @app.get("/api/admin/usuarios")
    async def admin_users(_: dict[str, Any] = Depends(require_admin)) -> list[dict[str, Any]]:
        try:
            return await auth_service.list_rebano_users()
        except IntegrationError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/api/admin/cameras")
    def admin_cameras(_: dict[str, Any] = Depends(require_admin)) -> list[dict[str, Any]]:
        return [camera_summary(camera_id, ctx) for camera_id, ctx in cameras.items()]

    @app.put("/api/admin/cameras/{camera_id}/vinculo")
    def link_camera(
        camera_id: str,
        body: CameraOwnerRequest,
        _: dict[str, Any] = Depends(require_admin),
    ) -> dict[str, Any]:
        get_camera(camera_id)
        db.set_camera_owner(camera_id, body.usuario_id, body.nome, body.email)
        return {"ok": True, "camera_id": camera_id, "usuario_id": body.usuario_id}

    @app.delete("/api/admin/cameras/{camera_id}/vinculo")
    def unlink_camera(
        camera_id: str,
        _: dict[str, Any] = Depends(require_admin),
    ) -> dict[str, Any]:
        get_camera(camera_id)
        db.remove_camera_owner(camera_id)
        return {"ok": True, "camera_id": camera_id}

    @app.post("/api/admin/contagem/resetar")
    def reset_all(_: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        return {"ok": True, "sessions": reset_all_callback()}

    # -------------------- Integracao servidor-a-servidor com o Rebano --------------------

    @app.get(
        "/api/integracao/usuarios/{usuario_id}/cameras",
        dependencies=[Depends(require_integration_key)],
    )
    def integration_cameras(usuario_id: int) -> list[dict[str, Any]]:
        return cameras_for_user(usuario_id)

    @app.get(
        "/api/integracao/usuarios/{usuario_id}/cameras/{camera_id}/frame.jpg",
        dependencies=[Depends(require_integration_key)],
    )
    def integration_frame(usuario_id: int, camera_id: str) -> Response:
        return jpeg_response(require_owner(camera_id, usuario_id))

    @app.get(
        "/api/integracao/usuarios/{usuario_id}/cameras/{camera_id}/stream.mjpg",
        dependencies=[Depends(require_integration_key)],
    )
    def integration_stream(usuario_id: int, camera_id: str) -> StreamingResponse:
        return mjpeg_response(require_owner(camera_id, usuario_id))

    @app.get(
        "/api/integracao/usuarios/{usuario_id}/cameras/{camera_id}/eventos",
        dependencies=[Depends(require_integration_key)],
    )
    def integration_events(
        usuario_id: int,
        camera_id: str,
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> list[dict[str, Any]]:
        require_owner(camera_id, usuario_id)
        return db.list_events(limit=limit, camera_id=camera_id)

    # -------------------- Diagnostico --------------------

    @app.get("/health")
    def health() -> dict[str, Any]:
        snapshots = [ctx["state"].snapshot() for ctx in cameras.values()]
        running = sum(1 for snap in snapshots if snap["sistema_rodando"])
        return {
            "status": "ok" if running else "degraded",
            "versao": "5.0.0",
            "cameras_configuradas": len(snapshots),
            "cameras_rodando": running,
        }

    @app.get("/api/admin/eventos/{event_id}/snapshot", dependencies=[Depends(require_admin)])
    def event_snapshot(event_id: int):
        event = db.get_event(event_id)
        if event is None or not event.get("snapshot_path"):
            raise HTTPException(status_code=404, detail="Snapshot nao encontrado")
        path = Path(event["snapshot_path"])
        if not path.exists():
            raise HTTPException(status_code=404, detail="Arquivo nao encontrado")
        return FileResponse(path)

    return app
