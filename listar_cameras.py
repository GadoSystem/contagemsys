"""Utilitario simples para descobrir indices de webcams disponiveis no Windows/Linux."""
from __future__ import annotations

import argparse
import cv2


def main() -> int:
    parser = argparse.ArgumentParser(description="Procura webcams pelos indices do OpenCV")
    parser.add_argument("--max", type=int, default=10, dest="max_index")
    args = parser.parse_args()

    encontradas: list[int] = []
    print(f"Procurando cameras nos indices 0 ate {args.max_index - 1}...")
    for index in range(max(1, args.max_index)):
        cap = cv2.VideoCapture(index)
        if cap.isOpened():
            ok, frame = cap.read()
            if ok and frame is not None:
                h, w = frame.shape[:2]
                encontradas.append(index)
                print(f"  [OK] source: {index} -> {w}x{h}")
            cap.release()
        else:
            cap.release()

    if not encontradas:
        print("Nenhuma webcam foi encontrada.")
        return 1

    print("\nUse estes indices em video.cameras[].source no config.yaml:")
    print(", ".join(str(i) for i in encontradas))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
