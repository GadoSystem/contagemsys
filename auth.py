from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import jwt


class AuthenticationError(Exception):
    pass


class IntegrationError(Exception):
    pass


class AuthService:
    """Autenticacao do ContagemSys usando os usuarios do Rebano.

    O ContagemSys nao armazena senha de fazendeiro. O login e validado no backend
    do Rebano e, se estiver correto, o ContagemSys emite um token proprio para a
    sessao web. O ID usado para vincular cameras e sempre o Usuario.Id do Rebano.
    """

    def __init__(
        self,
        *,
        rebano_api_url: str,
        jwt_secret: str,
        integration_key: str,
        admin_user: str,
        admin_password: str,
        token_minutes: int = 480,
    ) -> None:
        self.rebano_api_url = rebano_api_url.rstrip("/")
        self.jwt_secret = jwt_secret
        self.integration_key = integration_key
        self.admin_user = admin_user
        self.admin_password = admin_password
        self.token_minutes = max(15, int(token_minutes))

    def _issue_token(self, payload: dict[str, Any]) -> str:
        now = datetime.now(timezone.utc)
        data = {
            **payload,
            "iat": now,
            "exp": now + timedelta(minutes=self.token_minutes),
            "iss": "ContagemSys",
        }
        return jwt.encode(data, self.jwt_secret, algorithm="HS256")

    def decode_token(self, token: str) -> dict[str, Any]:
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=["HS256"],
                issuer="ContagemSys",
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Token invalido ou expirado") from exc
        return payload

    async def login_user(self, login: str, senha: str) -> dict[str, Any]:
        if not login.strip() or not senha:
            raise AuthenticationError("Informe login e senha")

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.post(
                    f"{self.rebano_api_url}/api/auth/login",
                    json={"login": login.strip(), "senha": senha},
                )
        except httpx.HTTPError as exc:
            raise IntegrationError("Nao foi possivel conectar ao Rebano") from exc

        if response.status_code == 401:
            raise AuthenticationError("Login ou senha invalidos")
        if response.status_code >= 400:
            raise IntegrationError(
                f"Rebano respondeu com erro {response.status_code}: {response.text[:200]}"
            )

        data = response.json()
        usuario = data.get("usuario") or {}
        usuario_id = usuario.get("id")
        if usuario_id is None:
            raise IntegrationError("Resposta de login do Rebano sem usuario.id")

        user_data = {
            "id": int(usuario_id),
            "nome": str(usuario.get("nome") or "Usuario"),
            "email": str(usuario.get("email") or ""),
        }
        token = self._issue_token(
            {
                "sub": str(user_data["id"]),
                "role": "user",
                "nome": user_data["nome"],
                "email": user_data["email"],
            }
        )
        return {"token": token, "usuario": user_data}

    def login_admin(self, usuario: str, senha: str) -> dict[str, Any]:
        if usuario != self.admin_user or senha != self.admin_password:
            raise AuthenticationError("Usuario ou senha de administrador invalidos")
        token = self._issue_token(
            {
                "sub": "admin",
                "role": "admin",
                "nome": self.admin_user,
            }
        )
        return {"token": token, "usuario": {"nome": self.admin_user, "role": "admin"}}

    async def list_rebano_users(self) -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(
                    f"{self.rebano_api_url}/api/integracao/usuarios",
                    headers={"X-Integration-Key": self.integration_key},
                )
        except httpx.HTTPError as exc:
            raise IntegrationError("Nao foi possivel consultar os usuarios do Rebano") from exc

        if response.status_code >= 400:
            raise IntegrationError(
                f"Rebano respondeu com erro {response.status_code}: {response.text[:200]}"
            )

        result: list[dict[str, Any]] = []
        for item in response.json():
            result.append(
                {
                    "id": int(item["id"]),
                    "nome": str(item.get("nome") or ""),
                    "email": str(item.get("email") or ""),
                }
            )
        return result
