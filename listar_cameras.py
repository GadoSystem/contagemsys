"""Scanner de dispositivos DirectShow sem reabrir a webcam durante o preview.

ATENCAO: um driver virtual como Iriun/OBS pode fornecer um quadro estatico
mesmo sem video real. Somente o usuario pode confirmar a origem visualmente.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import time

import cv2


def listar_nomes_windows() -> None:
    """Lista nomes amigaveis do Windows, SEM presumir sua ordem no OpenCV."""
    if os.name != "nt":
        return
    comando = r"Get-PnpDevice -PresentOnly | Where-Object { $_.Class -in @('Camera','Image') } | Select-Object -ExpandProperty FriendlyName"
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", comando],
            capture_output=True, text=True, errors="replace", timeout=8,
        )
        if result.returncode == 0 and result.stdout.strip():
            print("\nDispositivos que o Windows reconhece (ordem NAO equivale aos indices OpenCV):")
            for nome in result.stdout.splitlines():
                if nome.strip():
                    print(f"  - {nome.strip()}")
            print("Cameras virtuais (Iriun, OBS etc.) podem aparecer como webcam mesmo sem sinal.\n")
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass


def abrir(indice: int, backend: int | None):
    """Configura com os mesmos parametros de captura do sistema principal."""
    cap = cv2.VideoCapture(indice, backend) if backend is not None else cv2.VideoCapture(indice)
    if not cap.isOpened():
        cap.release()
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 20)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    return cap


def confirmar_frames(cap, prazo_segundos: float = 3.0) -> tuple[bool, object | None]:
    """Uma abertura; espera frames completos. Nao fecha/reabre antes do preview."""
    inicio = time.monotonic()
    validos = 0
    ultimo = None
    while time.monotonic() - inicio < prazo_segundos and validos < 5:
        ok, imagem = cap.read()
        if ok and imagem is not None and getattr(imagem, "size", 0):
            ultimo = imagem
            validos += 1
        else:
            time.sleep(0.06)
    return validos >= 3, ultimo


def preview_live(indice: int, cap, primeiro) -> int:
    """Mostra frames do MESMO cap. S aceita; N rejeita; Esc interrompe."""
    titulo = f"Fonte {indice} | S=SIM / N=NAO / ESC=SAIR"
    print("      Mova a mao em frente a lente. Se mostrar 'Iriun' sem imagem, marque N.")
    falhas = 0
    try:
        imagem = primeiro
        while True:
            if imagem is None:
                ok, imagem = cap.read()
                if not ok or imagem is None:
                    falhas += 1
                    if falhas >= 12:
                        print("      Dispositivo parou de entregar imagens. Rejeitado.")
                        return ord("n")
                    time.sleep(0.08)
                    continue
            falhas = 0
            mostra = imagem.copy()
            cv2.putText(mostra, f"FONTE {indice}  S=SIM / N=NAO / ESC=SAIR",
                        (12, 28), cv2.FONT_HERSHEY_SIMPLEX, .53, (0, 255, 255), 2)
            cv2.imshow(titulo, mostra)
            tecla = cv2.waitKey(20) & 0xFF
            if tecla in (ord("s"), ord("S"), ord("n"), ord("N"), 27):
                return tecla
            imagem = None
    finally:
        try:
            cv2.destroyWindow(titulo)
        except cv2.error:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Busca webcams e exige confirmacao visual")
    parser.add_argument("--max", type=int, default=8, dest="max_index")
    parser.add_argument("--backend", choices=["dshow", "msmf", "default"], default="dshow" if os.name == "nt" else "default")
    parser.add_argument("--preview", action="store_true", help="S confirma, N ignora, ESC encerra")
    parser.add_argument("--sync", action="store_true", help="Busca todas as fontes USB/virtuais/IP e atualiza config.yaml")
    parser.add_argument("--config", default="config.yaml", help="Config para --sync (padrao: config.yaml)")
    args = parser.parse_args()
    cv2.setNumThreads(1)
    if args.sync:
        from pathlib import Path
        from dotenv import load_dotenv
        from camera_discovery import discover_and_sync
        load_dotenv(Path(__file__).resolve().parent / ".env")
        discover_and_sync(Path(args.config))
        return 0
    codes = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF, "default": None}
    found = []
    print(f"Backend {args.backend.upper()} — indices 0..{max(1,args.max_index)-1}")
    print("PARE o ContagemSys antes do scanner e feche outros apps que usam webcams.")
    listar_nomes_windows()
    for index in range(max(1, args.max_index)):
        captura = abrir(index, codes[args.backend])
        if captura is None:
            print(f"  [-] {index}: dispositivo inexistente ou ocupado")
            continue
        try:
            ok, image = confirmar_frames(captura)
            if not ok or image is None:
                print(f"  [-] {index}: sem frames validos")
                continue
            h, w = image.shape[:2]
            print(f"  [?] source {index}: {w}x{h} — confirme se ha VIDEO REAL")
            if args.preview:
                tecla = preview_live(index, captura, image)
                if tecla == 27:
                    break
                if tecla not in (ord("s"), ord("S")):
                    print(f"      Fonte {index} ignorada.")
                    continue
            found.append(index)
        finally:
            captura.release()
    cv2.destroyAllWindows()
    print("\nFontes confirmadas: " + (", ".join(map(str, found)) or "nenhuma"))
    if not args.preview:
        print("Sem --preview, frames estaticos de cameras virtuais NAO sao descartados.")
    print("Configure apenas indices confirmados em video.cameras[].source.")
    return 0 if found else 1


if __name__ == "__main__":
    raise SystemExit(main())
