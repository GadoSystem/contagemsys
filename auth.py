from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import jwt


class AuthenticationError(Exception):
    pass


class IntegrationError(Exception):
    pass


class LoginInputError(Exception):
    """Dados de login vazios ou com formato invalido (nada e enviado ao Rebano)."""


# Aceita somente "00000000000" ou "000.000.000-00" (mascara parcial tambem).
_CPF_FORMATO = re.compile(r"^\d{3}\.?\d{3}\.?\d{3}-?\d{2}$")


def normalizar_cpf(valor: str | None) -> str | None:
    """Retorna os 11 digitos do CPF ou None quando o formato e invalido.

    Usa a mesma regra do cadastro do Rebano: 11 digitos, nao repetidos, com os
    digitos verificadores corretos.
    """
    texto = (valor or "").strip()
    if not _CPF_FORMATO.match(texto):
        return None
    digitos = re.sub(r"\D", "", texto)
    if len(set(digitos)) == 1:
        return None
    for tamanho in (9, 10):
        soma = sum(int(d) * peso for d, peso in zip(digitos[:tamanho], range(tamanho + 1, 1, -1)))
        resto = soma % 11
        if digitos[tamanho] != str(0 if resto < 2 else 11 - resto):
            return None
    return digitos


def formatar_cpf(digitos: str) -> str:
    """Formato gravado pelo Rebano: 000.000.000-00."""
    return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"


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
        # Token do Rebano de cada usuario logado, mantido SOMENTE em memoria do
        # servidor (nunca vai para a tela nem para o token do ContagemSys). Serve
        # para consultar as fazendas e cameras do proprio usuario no Rebano.
        self._sessoes_rebano: dict[int, dict[str, Any]] = {}
        self.fazendas_ttl_segundos = 60.0
        self.fazendas_retry_segundos = 15.0

    def _issue_token(self, payload: dict[str, Any]) -> str:
        now = datetime.now(timezone.utc)
        data = {
            **payload,
            "iat": now,
            "exp": now + timedelta(minutes=self.token_minutes),
            "iss": "ContagemSys",
        }
        return jwt.encode(data, self.jwt_secret, algorithm="HS256")

    def issue_stream_ticket(self, usuario_id: int, camera_id: str) -> str:
        """Token limitado a uma unica camera e com validade curta (2 minutos).

        O token permite iniciar um stream em <img>, que nao envia Authorization.
        """
        now = datetime.now(timezone.utc)
        return jwt.encode(
            {"role": "stream", "sub": str(usuario_id), "camera_id": camera_id,
             "iss": "ContagemSys", "iat": now, "exp": now + timedelta(minutes=2)},
            self.jwt_secret, algorithm="HS256",
        )

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

    async def login_user(self, cpf: str, senha: str) -> dict[str, Any]:
        """Login por CPF + senha. A senha e sempre verificada pelo Rebano.

        O endpoint /api/auth/login do Rebano aceita o CPF diretamente (com ou sem
        mascara), entao nao e preciso consultar o banco do Rebano.
        """
        if not (cpf or "").strip() or not senha:
            raise LoginInputError("Informe o CPF e a senha")
        digitos = normalizar_cpf(cpf)
        if digitos is None:
            raise LoginInputError("CPF invalido. Informe os 11 digitos, com ou sem mascara.")

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.post(
                    f"{self.rebano_api_url}/api/auth/login",
                    json={"login": formatar_cpf(digitos), "senha": senha},
                )
        except httpx.HTTPError as exc:
            raise IntegrationError("Nao foi possivel conectar ao Rebano") from exc

        if response.status_code == 401:
            raise AuthenticationError("CPF ou senha incorretos")
        if response.status_code >= 400:
            raise IntegrationError(
                f"Rebano respondeu com erro {response.status_code}: {response.text[:200]}"
            )

        data = response.json()
        usuario = data.get("usuario") or {}
        usuario_id = usuario.get("id")
        if usuario_id is None:
            raise IntegrationError("Resposta de login do Rebano sem usuario.id")
        # Com 11 digitos o Rebano tambem tenta o numero como telefone; so aceita
        # a conta cujo CPF e exatamente o informado.
        if re.sub(r"\D", "", str(usuario.get("cpf") or "")) != digitos:
            raise AuthenticationError("CPF ou senha incorretos")

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
        rebano_token = data.get("token")
        if rebano_token:
            self._sessoes_rebano[user_data["id"]] = {"token": str(rebano_token), "mapa": None, "proxima": 0.0}
            # Pre-carrega o agrupamento; uma falha aqui nao impede o login.
            await self.fazendas_das_cameras(user_data["id"])
        return {"token": token, "usuario": user_data}

    async def fazendas_das_cameras(self, usuario_id: int) -> dict[str, dict[str, Any]] | None:
        """Mapa identificacao da camera (casefold) -> fazenda do usuario no Rebano.

        Usa o token do Rebano obtido no login. Retorna None quando nao ha sessao do
        Rebano em memoria (ex.: ContagemSys reiniciado) e o ultimo mapa conhecido
        quando o Rebano esta indisponivel.
        """
        sessao = self._sessoes_rebano.get(int(usuario_id))
        if sessao is None:
            return None
        agora = time.monotonic()
        if agora < sessao["proxima"]:
            return sessao["mapa"]
        try:
            sessao["mapa"] = await self._buscar_fazendas(sessao["token"])
            sessao["proxima"] = agora + self.fazendas_ttl_segundos
        except AuthenticationError:
            # Token do Rebano expirado: so um novo login renova o agrupamento.
            self._sessoes_rebano.pop(int(usuario_id), None)
            return None
        except IntegrationError:
            sessao["proxima"] = agora + self.fazendas_retry_segundos
        return sessao["mapa"]

    async def _buscar_fazendas(self, rebano_token: str) -> dict[str, dict[str, Any]]:
        """GET /Fazenda/ObterTodos (fazendas do usuario) + GET /Fazenda/{id}/Cameras."""
        headers = {"Authorization": f"Bearer {rebano_token}"}
        try:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
                response = await client.get(f"{self.rebano_api_url}/Fazenda/ObterTodos", headers=headers)
                if response.status_code == 401:
                    raise AuthenticationError("Sessao do Rebano expirada")
                if response.status_code >= 400:
                    raise IntegrationError(f"Rebano respondeu com erro {response.status_code}")
                fazendas = [f for f in response.json() if isinstance(f, dict) and f.get("id") is not None]
                respostas = await asyncio.gather(*(
                    client.get(f"{self.rebano_api_url}/Fazenda/{int(f['id'])}/Cameras", headers=headers)
                    for f in fazendas
                ))
        except httpx.HTTPError as exc:
            raise IntegrationError("Nao foi possivel consultar as fazendas no Rebano") from exc
        except ValueError as exc:
            raise IntegrationError("Resposta de fazendas do Rebano invalida") from exc

        mapa: dict[str, dict[str, Any]] = {}
        for fazenda, resposta in zip(fazendas, respostas):
            if resposta.status_code != 200:
                continue
            info = {"id": int(fazenda["id"]), "nome": str(fazenda.get("nome") or f"Fazenda {fazenda['id']}")}
            for camera in resposta.json():
                identificacao = str((camera or {}).get("identificacao") or "").strip().casefold()
                if identificacao:
                    mapa.setdefault(identificacao, info)
        return mapa

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
