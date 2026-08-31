from ultralytics import YOLO

from config import load_config


if __name__ == "__main__":
    cfg = load_config()
    model = YOLO(cfg["model"]["path"])
    exported = model.export(format="onnx", imgsz=cfg["model"]["imgsz"], dynamic=True)
    print(f"Modelo ONNX exportado para: {exported}")
