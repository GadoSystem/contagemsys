from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

BASE_DIR = Path(__file__).resolve().parent

DEFAULT_CONFIG: dict[str, Any] = {
    "app": {"name": "Contagem V3", "host": "127.0.0.1", "port": 8000, "show_window": True},
    "display": {
        "sidebar": {"enabled": True, "width": 300, "position": "left"},
    },
    "video": {"source": 0, "width": 1280, "height": 720, "inference_stride": 1},
    "model": {
        "path": "yolo26n.pt", "classes": [0], "confidence": 0.35,
        "imgsz": 416, "device": None, "tracker": "tracker_bytetrack.yaml",
    },
    "roi": {"enabled": False, "x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 1.0},
    "gate": {
        "left_x": 0.42, "right_x": 0.58, "stable_frames": 2,
        "stale_after_frames": 120, "count_direction": "right_to_left",
        "anchor": "bottom_center",
    },
    "persistence": {"database": "data/contagem.db", "max_api_events": 200},
    "evidence": {
        "enabled": True, "directory": "eventos", "save_snapshot": True,
        "save_clip": True, "pre_seconds": 3.0, "post_seconds": 3.0, "clip_fps": 20.0,
    },
}


def _merge(base: dict[str, Any], custom: dict[str, Any]) -> dict[str, Any]:
    for key, value in custom.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    cfg = deepcopy(DEFAULT_CONFIG)
    config_path = Path(path) if path else BASE_DIR / "config.yaml"
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as fh:
            custom = yaml.safe_load(fh) or {}
        _merge(cfg, custom)

    gate = cfg["gate"]
    if not 0 <= gate["left_x"] < gate["right_x"] <= 1:
        raise ValueError("gate.left_x e gate.right_x devem respeitar 0 <= left < right <= 1")
    if int(gate["stable_frames"]) < 1:
        raise ValueError("gate.stable_frames deve ser >= 1")

    roi = cfg["roi"]
    if not (0 <= roi["x1"] < roi["x2"] <= 1 and 0 <= roi["y1"] < roi["y2"] <= 1):
        raise ValueError("ROI deve usar coordenadas normalizadas validas entre 0 e 1")
    return cfg


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


def resolve_tracker(value: str) -> str:
    local = BASE_DIR / value
    return str(local) if local.exists() else value
