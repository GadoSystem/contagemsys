"""
Guarda o resultado da contagem em um lugar só, de forma segura para
ser lido/escrito ao mesmo tempo pela thread do vídeo (OpenCV/YOLO)
e pela thread da API (FastAPI).
"""

import threading
from datetime import datetime


class ContagemState:
    def __init__(self):
        self._lock = threading.Lock()
        self._total_atual = 0        # animais únicos contados até agora
        self._no_frame_agora = 0     # quantos animais aparecem no frame atual
        self._maior_contagem = 0     # maior valor já visto (pico)
        self._ultima_atualizacao = None
        self._rodando = False

    def atualizar(self, total_unico: int, no_frame: int):
        with self._lock:
            self._total_atual = total_unico
            self._no_frame_agora = no_frame
            self._maior_contagem = max(self._maior_contagem, total_unico)
            self._ultima_atualizacao = datetime.now().isoformat()
            self._rodando = True

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "total_unico": self._total_atual,
                "animais_no_frame_agora": self._no_frame_agora,
                "maior_contagem_ja_vista": self._maior_contagem,
                "ultima_atualizacao": self._ultima_atualizacao,
                "sistema_rodando": self._rodando,
            }

    def resetar(self):
        with self._lock:
            self._total_atual = 0
            self._no_frame_agora = 0
            self._maior_contagem = 0
            self._ultima_atualizacao = datetime.now().isoformat()


# instância única, compartilhada entre os arquivos do projeto
estado = ContagemState()
