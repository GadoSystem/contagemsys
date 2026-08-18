"""
LEITOR DE CÂMERA EM TEMPO REAL (sem acúmulo de atraso)
========================================================

Por que a versão anterior travava:
Antes, o programa lia um frame da câmera -> rodava a IA nele (o passo mais
lento) -> mostrava na tela -> lia o PRÓXIMO frame -> repetia. Só que a
câmera do celular continua mandando frames novos o tempo todo, mesmo
enquanto a IA ainda está processando o frame anterior. Esses frames vão
se acumulando numa fila interna do OpenCV, e o programa insiste em
processar TODOS eles, em ordem — o resultado é um atraso que só cresce
(o vídeo "trava" e fica cada v5vez mais fora do tempo real).

A solução (padrão "producer-consumer com descarte de frame"):
Essa classe roda em uma THREAD separada, só de ler a câmera, o mais
rápido possível, e guarda apenas o ÚLTIMO frame lido. O restante do
programa (que roda a IA) sempre pega o frame mais atual disponível e
IGNORA os frames antigos que não deu tempo de processar. Ou seja, a
gente troca "processar 100% dos frames" por "estar sempre em tempo
real" — que é o que importa numa câmera de segurança ao vivo.
"""

import threading
import time

import cv2


class LeitorCamera:
    def __init__(self, fonte, largura_alvo=None):
        """
        fonte: 0, 1, 2... (índice de webcam) ou uma URL (rtsp://, http://)
        largura_alvo: se definido, reduz cada frame para essa largura
                      (mantendo a proporção) assim que ele chega —
                      MUITO importante para performance, já que celulares
                      costumam mandar vídeo em resolução bem mais alta
                      do que o necessário para a IA detectar os animais.
        """
        self.fonte = fonte
        self.largura_alvo = largura_alvo
        self.captura = cv2.VideoCapture(fonte)

        # tenta pedir pro driver da câmera manter só 1 frame de buffer
        # (nem todo backend/câmera respeita isso, mas não custa tentar)
        self.captura.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not self.captura.isOpened():
            raise RuntimeError(
                f"Não consegui abrir a fonte de vídeo: {fonte!r}. "
                "Confira se o número/URL da câmera está certo e se ela "
                "está ligada/conectada na mesma rede."
            )

        self._lock = threading.Lock()
        self._frame_atual = None
        self._rodando = False
        self._thread = None
        self.fps_captura = 0.0

    def iniciar(self):
        self._rodando = True
        self._thread = threading.Thread(target=self._loop_captura, daemon=True)
        self._thread.start()
        return self

    def _loop_captura(self):
        contador = 0
        marco_tempo = time.time()

        while self._rodando:
            ok, frame = self.captura.read()
            if not ok:
                # câmera sem frame novo no momento (comum em streams de
                # celular via wifi) — espera um pouquinho e tenta de novo
                time.sleep(0.05)
                continue

            if self.largura_alvo and frame.shape[1] > self.largura_alvo:
                escala = self.largura_alvo / frame.shape[1]
                nova_altura = int(frame.shape[0] * escala)
                frame = cv2.resize(frame, (self.largura_alvo, nova_altura))

            with self._lock:
                self._frame_atual = frame

            # calcula o fps real de chegada de frames (só informativo)
            contador += 1
            if time.time() - marco_tempo >= 1.0:
                self.fps_captura = contador / (time.time() - marco_tempo)
                contador = 0
                marco_tempo = time.time()

    def ultimo_frame(self):
        """Devolve o frame mais recente disponível (ou None se ainda não chegou nenhum)."""
        with self._lock:
            return None if self._frame_atual is None else self._frame_atual.copy()

    def parar(self):
        self._rodando = False
        if self._thread is not None:
            self._thread.join(timeout=1)
        self.captura.release()
