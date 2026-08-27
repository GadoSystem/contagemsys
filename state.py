"""Estado compartilhado entre a visão computacional e a API FastAPI."""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime
from typing import Deque, Dict, List, Optional


class ContagemState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total = 0
        self._no_frame = 0
        self._maior_contagem = 0
        self._retornos = 0
        self._fps_ia = 0.0
        self._fps_camera = 0.0
        self._latencia_ms = 0.0
        self._ultima_atualizacao: Optional[str] = None
        self._rodando = False
        self._reset_version = 0
        self._eventos: Deque[Dict] = deque(maxlen=100)

    def atualizar(
        self,
        *,
        total: int,
        no_frame: int,
        retornos: int,
        fps_ia: float,
        fps_camera: float,
        latencia_ms: float,
        reset_version: int,
    ) -> bool:
        """Atualiza o estado somente se pertencer à sessão atual.

        Isso evita que um frame que estava sendo inferido antes de um POST /resetar
        sobrescreva o zero da nova sessão ao terminar o processamento.
        """
        with self._lock:
            if reset_version != self._reset_version:
                return False
            self._total = int(total)
            self._no_frame = int(no_frame)
            self._retornos = int(retornos)
            self._fps_ia = float(fps_ia)
            self._fps_camera = float(fps_camera)
            self._latencia_ms = float(latencia_ms)
            self._maior_contagem = max(self._maior_contagem, self._total)
            self._ultima_atualizacao = datetime.now().isoformat()
            self._rodando = True
            return True

    def registrar_evento(self, evento: Dict, reset_version: int) -> None:
        with self._lock:
            if reset_version != self._reset_version:
                return
            item = dict(evento)
            item["timestamp"] = datetime.now().isoformat()
            self._eventos.appendleft(item)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                # Mantido por compatibilidade com o endpoint antigo.
                "total_unico": self._total,
                "total_contado": self._total,
                "animais_no_frame_agora": self._no_frame,
                "maior_contagem_ja_vista": self._maior_contagem,
                "retornos_esquerda_para_direita": self._retornos,
                "direcao_contada": "direita_para_esquerda",
                "fps_ia": round(self._fps_ia, 2),
                "fps_camera": round(self._fps_camera, 2),
                "latencia_ia_ms": round(self._latencia_ms, 1),
                "ultima_atualizacao": self._ultima_atualizacao,
                "sistema_rodando": self._rodando,
            }

    def eventos(self) -> List[Dict]:
        with self._lock:
            return list(self._eventos)

    def resetar(self) -> int:
        with self._lock:
            self._reset_version += 1
            self._total = 0
            self._no_frame = 0
            self._maior_contagem = 0
            self._retornos = 0
            self._eventos.clear()
            self._ultima_atualizacao = datetime.now().isoformat()
            return self._reset_version

    def reset_version(self) -> int:
        with self._lock:
            return self._reset_version

    def marcar_parado(self) -> None:
        with self._lock:
            self._rodando = False


estado = ContagemState()
