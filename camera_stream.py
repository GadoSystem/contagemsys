"""Captura de câmera em thread com descarte de frames antigos.

A IA nunca consome uma fila atrasada: ela sempre pega o pacote mais novo.
Cada pacote recebe um número de sequência para impedir que o mesmo frame seja
inferido duas vezes quando a câmera está entregando menos FPS que o loop.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Optional, Union

import cv2


@dataclass
class FramePacket:
    seq: int
    captured_at: float
    frame: object


class LeitorCamera:
    def __init__(
        self,
        fonte: Union[int, str],
        largura_alvo: Optional[int] = 640,
        altura_alvo: Optional[int] = 480,
        fps_alvo: Optional[int] = 30,
    ) -> None:
        self.fonte = fonte
        self.largura_alvo = largura_alvo
        self.altura_alvo = altura_alvo
        self.fps_alvo = fps_alvo
        self.captura = self._abrir_captura(fonte)

        self.captura.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if largura_alvo:
            self.captura.set(cv2.CAP_PROP_FRAME_WIDTH, largura_alvo)
        if altura_alvo:
            self.captura.set(cv2.CAP_PROP_FRAME_HEIGHT, altura_alvo)
        if fps_alvo:
            self.captura.set(cv2.CAP_PROP_FPS, fps_alvo)

        # Em webcams USB no Windows, MJPG costuma reduzir uso de banda/CPU.
        if isinstance(fonte, int):
            self.captura.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

        if not self.captura.isOpened():
            raise RuntimeError(f"Não consegui abrir a fonte de vídeo: {fonte!r}.")

        self._lock = threading.Lock()
        self._packet: Optional[FramePacket] = None
        self._rodando = False
        self._thread: Optional[threading.Thread] = None
        self.fps_captura = 0.0

    @staticmethod
    def _abrir_captura(fonte):
        # DirectShow tende a ter menor latência para webcam física no Windows.
        if os.name == "nt" and isinstance(fonte, int):
            captura = cv2.VideoCapture(fonte, cv2.CAP_DSHOW)
            if captura.isOpened():
                return captura
            captura.release()
        return cv2.VideoCapture(fonte)

    def iniciar(self):
        self._rodando = True
        self._thread = threading.Thread(target=self._loop_captura, daemon=True)
        self._thread.start()
        return self

    def _loop_captura(self) -> None:
        contador = 0
        marco_tempo = time.perf_counter()
        seq = 0

        while self._rodando:
            ok, frame = self.captura.read()
            if not ok:
                time.sleep(0.02)
                continue

            # Caso o driver ignore a resolução pedida, reduzimos aqui.
            if self.largura_alvo and frame.shape[1] > self.largura_alvo:
                escala = self.largura_alvo / frame.shape[1]
                nova_altura = int(frame.shape[0] * escala)
                frame = cv2.resize(
                    frame,
                    (self.largura_alvo, nova_altura),
                    interpolation=cv2.INTER_AREA,
                )

            seq += 1
            packet = FramePacket(seq=seq, captured_at=time.perf_counter(), frame=frame)
            with self._lock:
                self._packet = packet

            contador += 1
            agora = time.perf_counter()
            janela = agora - marco_tempo
            if janela >= 1.0:
                self.fps_captura = contador / janela
                contador = 0
                marco_tempo = agora

    def ultimo_pacote(self) -> Optional[FramePacket]:
        with self._lock:
            if self._packet is None:
                return None
            return FramePacket(
                seq=self._packet.seq,
                captured_at=self._packet.captured_at,
                frame=self._packet.frame.copy(),
            )

    def ultimo_frame(self):
        packet = self.ultimo_pacote()
        return None if packet is None else packet.frame

    def parar(self) -> None:
        self._rodando = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self.captura.release()
