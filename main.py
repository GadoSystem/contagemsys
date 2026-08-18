"""
CONTADOR DE ANIMAIS EM TEMPO REAL
==================================
Tecnologias usadas e o papel de cada uma:

- Python              -> a linguagem/cola de tudo
- OpenCV              -> lê a câmera e mostra a janela com data/hora + contagem
- Ultralytics YOLO    -> detecta os animais em cada frame
- ByteTrack/BoT-SORT  -> dá um ID único pra cada animal (não conta o mesmo 2x)
- FastAPI             -> expõe a contagem como uma API, rodando junto
- threading (Python)  -> roda a câmera, a IA e a API em paralelo, sem travar

Como rodar:
    python main.py

Como parar:
    clique na janela de vídeo e aperte a tecla 'q'
    (ou Ctrl+C no terminal)
"""

import threading
import time
from datetime import datetime

import cv2
import uvicorn
from ultralytics import YOLO

from api import app
from camera_stream import LeitorCamera
from state import estado

# ============================================================
#  CONFIGURAÇÕES — é aqui que você mexe para trocar de câmera
# ============================================================

# Fonte do vídeo:
#   0                                  -> webcam do notebook (padrão)
#   1, 2...                            -> outras webcams/câmeras virtuais (ex: Iriun, Continuity Camera)
#   "http://192.168.0.15:8080/video"   -> celular Android com app "IP Webcam"
#   "rtsp://192.168.0.15:8554/live"    -> celular com app de câmera IP via RTSP
FONTE_VIDEO = 0

# Modelo YOLO. "yolo26n.pt" é o menor/mais rápido (bom para notebook/CPU).
MODELO = "yolo26n.pt"

# Classes do COCO que queremos detectar (modelo genérico, sem treino extra).
#   0  = person (pessoa)   -> ótimo para TESTAR o pipeline sem ter animal por perto
#   17 = horse  (cavalo)
#   18 = sheep  (ovelha)
#   19 = cow    (vaca/boi/gado)
CLASSES_ALVO = [0]

# Tracker: "bytetrack.yaml" (leve/rápido, padrão recomendado para CPU) ou
# "botsort.yaml" (mais robusto a oclusão entre animais parecidos, porém mais pesado).
# Se ainda estiver lento, deixe em bytetrack. Se estiver rápido mas trocando
# de ID muito (animais se cruzando), aí sim vale testar botsort.
TRACKER = "bytetrack.yaml"

# Confiança mínima para considerar uma detecção válida (0 a 1)
CONFIANCA_MINIMA = 0.4

# --- Ajustes de PERFORMANCE (as principais mudanças contra o travamento) ---

# Reduz a largura do frame ANTES de mandar para a IA. Celulares costumam
# mandar vídeo em 1080p+ e isso sozinho já deixa tudo lento. 640 é um bom
# equilíbrio entre nitidez e velocidade; em notebook fraco, tente 480.
LARGURA_PROCESSAMENTO = 640

# Resolução interna usada pelo YOLO para processar cada frame (não precisa
# bater com LARGURA_PROCESSAMENTO). Menor = mais rápido, porém pode perder
# animais pequenos/distantes no quadro.
IMGSZ = 480

# Quantos frames pular entre uma detecção e outra. 0 = analisa todo frame
# disponível (mais preciso). 1 = analisa 1 a cada 2 (2x mais rápido, ainda
# mostra vídeo fluido, só a contagem atualiza um pouco menos vezes por
# segundo). Suba esse número se o PC for fraco.
PULAR_FRAMES = 0

# ============================================================


def iniciar_api():
    """Roda o servidor FastAPI em segundo plano (thread separada)."""
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")


def desenhar_overlay(frame, total_unico: int, maior_contagem: int, no_frame: int, fps: float):
    """Desenha a faixa preta no topo com data/hora e os números da contagem."""
    agora = datetime.now().strftime("%d/%m/%Y  %H:%M:%S")
    largura = frame.shape[1]

    cv2.rectangle(frame, (0, 0), (largura, 70), (0, 0, 0), -1)

    cv2.putText(
        frame, agora, (15, 28),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2,
    )

    texto = (
        f"No frame: {no_frame}   |   Total unico: {total_unico}   |   "
        f"Maior ja visto: {maior_contagem}   |   FPS: {fps:.1f}"
    )
    cv2.putText(
        frame, texto, (15, 56),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2,
    )
    return frame


def main():
    # 1) sobe a API em segundo plano
    thread_api = threading.Thread(target=iniciar_api, daemon=True)
    thread_api.start()
    print("=" * 60)
    print("API disponível em:      http://localhost:8000/docs")
    print("Contagem em tempo real: http://localhost:8000/contagem/atual")
    print("=" * 60)

    # 2) carrega o modelo YOLO (baixa automaticamente na 1a vez)
    print(f"Carregando modelo {MODELO} ...")
    modelo = YOLO(MODELO)

    # 3) inicia a câmera em thread própria, com descarte de frames antigos
    print(f"Conectando na fonte de vídeo: {FONTE_VIDEO}")
    camera = LeitorCamera(FONTE_VIDEO, largura_alvo=LARGURA_PROCESSAMENTO).iniciar()

    print("Aguardando o primeiro frame da câmera...")
    tentativas = 0
    while camera.ultimo_frame() is None:
        time.sleep(0.1)
        tentativas += 1
        if tentativas > 100:  # ~10 segundos
            raise RuntimeError(
                "Não chegou nenhum frame da câmera em 10s. Confira a FONTE_VIDEO."
            )

    print("Câmera conectada! Uma janela vai abrir. Pressione 'q' para encerrar.\n")

    ids_unicos = set()
    contador_frames = 0
    ultimo_tempo = time.time()
    fps_exibicao = 0.0

    try:
        while True:
            frame = camera.ultimo_frame()
            if frame is None:
                continue

            contador_frames += 1
            pular_este_frame = PULAR_FRAMES and (contador_frames % (PULAR_FRAMES + 1) != 0)

            if pular_este_frame:
                # mostra o frame cru (sem rodar IA nele) pra manter o vídeo fluido
                frame_exibido = frame
                no_frame = 0
            else:
                resultados = modelo.track(
                    frame,
                    classes=CLASSES_ALVO,
                    conf=CONFIANCA_MINIMA,
                    tracker=TRACKER,
                    imgsz=IMGSZ,
                    persist=True,
                    verbose=False,
                )
                r = resultados[0]
                frame_exibido = r.plot()

                no_frame = 0
                if r.boxes is not None and r.boxes.id is not None:
                    for box_id in r.boxes.id:
                        ids_unicos.add(int(box_id))
                        no_frame += 1

                estado.atualizar(total_unico=len(ids_unicos), no_frame=no_frame)

            # fps real de exibição (quantos frames por segundo o loop consegue processar)
            agora = time.time()
            if agora - ultimo_tempo > 0:
                fps_exibicao = 0.9 * fps_exibicao + 0.1 * (1.0 / (agora - ultimo_tempo))
            ultimo_tempo = agora

            frame_exibido = desenhar_overlay(
                frame_exibido,
                total_unico=len(ids_unicos),
                maior_contagem=estado.snapshot()["maior_contagem_ja_vista"],
                no_frame=no_frame,
                fps=fps_exibicao,
            )

            cv2.imshow("Contagem de Animais - pressione 'q' para sair", frame_exibido)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        camera.parar()
        cv2.destroyAllWindows()
        print(f"\nEncerrado. Total de animais únicos contados nesta sessão: {len(ids_unicos)}")


if __name__ == "__main__":
    main()
