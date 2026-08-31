from ultralytics import YOLO

from config import load_config


if __name__ == "__main__":
    cfg = load_config()
    model_path = cfg["model"]["path"]
    model = YOLO(model_path)
    exported = model.export(format="openvino", imgsz=cfg["model"]["imgsz"], half=False)
    print(f"Modelo OpenVINO exportado para: {exported}")
