"""Exporta o detector para OpenVINO (opcional, indicado principalmente para CPU Intel).

Uso:
    pip install openvino
    python export_openvino.py

Depois troque MODELO em main.py para a pasta criada, normalmente:
    MODELO = "yolo26n_openvino_model"
"""

from ultralytics import YOLO

MODELO_ORIGEM = "yolo26n.pt"
IMGSZ = 416

if __name__ == "__main__":
    model = YOLO(MODELO_ORIGEM)
    caminho = model.export(format="openvino", imgsz=IMGSZ, dynamic=False)
    print(f"Modelo OpenVINO exportado em: {caminho}")
