from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
import re

import yaml

BASE_DIR = Path(__file__).resolve().parent
CAMERA_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

DEFAULT_CONFIG: dict[str, Any] = {
    "app": {
        "name": "Contagem V4",
        "host": "0.0.0.0",
        "port": 8000,
        "show_window": True,
    },
    "api": {
        "auth": {
            "enabled": True,
            "api_key_env": "CONTAGEM_API_KEY",
        },
        "jpeg_quality": 72,
        "stream_fps": 10,
        "include_sidebar": False,
    },
    "display": {
        "preview_fps": 20,
        "max_box_age_ms": 700,
        "sidebar": {"enabled": True, "width": 300, "position": "left"},
    },
    "performance": {
        "max_concurrent_inferences": 1,
        "torch_threads": 0,
        "opencv_threads": 1,
    },
    "video": {
        "width": 640,
        "height": 480,
        "fps": 30,
        "backend": "auto",
        "fourcc": "MJPG",
        "inference_fps": 6.0,
        "inference_stride": 1,
        "cameras": [
            {"id": "camera_1", "name": "Camera 1", "source": 0, "enabled": True},
        ],
    },
    "model": {
        "path": "yolo26n.pt",
        "classes": [0],
        "confidence": 0.35,
        "imgsz": 320,
        "device": None,
        "tracker": "tracker_bytetrack.yaml",
    },
    "roi": {"enabled": False, "x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 1.0},
    "gate": {
        "left_x": 0.42,
        "right_x": 0.58,
        "stable_frames": 2,
        "stale_after_frames": 120,
        "count_direction": "right_to_left",
        "anchor": "bottom_center",
    },
    "persistence": {"database": "data/contagem.db", "max_api_events": 200},
    "evidence": {
        "enabled": True,
        "directory": "eventos",
        "save_snapshot": True,
        "save_clip": True,
        "pre_seconds": 3.0,
        "post_seconds": 3.0,
        "clip_fps": 20.0,
    },
}


def _merge(base: dict[str, Any], custom: dict[str, Any]) -> dict[str, Any]:
    for key, value in custom.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def _validate_gate(gate: dict[str, Any], prefix: str = "gate") -> None:
    if not 0 <= float(gate["left_x"]) < float(gate["right_x"]) <= 1:
        raise ValueError(f"{prefix}.left_x e {prefix}.right_x devem respeitar 0 <= left < right <= 1")
    if int(gate["stable_frames"]) < 1:
        raise ValueError(f"{prefix}.stable_frames deve ser >= 1")
    if int(gate["stale_after_frames"]) < 1:
        raise ValueError(f"{prefix}.stale_after_frames deve ser >= 1")


def _validate_roi(roi: dict[str, Any], prefix: str = "roi") -> None:
    if not (
        0 <= float(roi["x1"]) < float(roi["x2"]) <= 1
        and 0 <= float(roi["y1"]) < float(roi["y2"]) <= 1
    ):
        raise ValueError(f"{prefix} deve usar coordenadas normalizadas validas entre 0 e 1")


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    cfg = deepcopy(DEFAULT_CONFIG)
    config_path = Path(path) if path else BASE_DIR / "config.yaml"
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as fh:
            custom = yaml.safe_load(fh) or {}
        _merge(cfg, custom)

    # Compatibilidade com configuracoes antigas que usavam video.source.
    video = cfg.setdefault("video", {})
    if "cameras" not in video or not video["cameras"]:
        legacy_source = video.get("source", 0)
        video["cameras"] = [
            {"id": "camera_1", "name": "Camera 1", "source": legacy_source, "enabled": True}
        ]

    _validate_gate(cfg["gate"])
    _validate_roi(cfg["roi"])

    seen_ids: set[str] = set()
    enabled_count = 0
    normalized_cameras: list[dict[str, Any]] = []

    for index, raw in enumerate(video["cameras"], start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"video.cameras[{index}] deve ser um objeto YAML")

        camera = deepcopy(raw)
        camera_id = str(camera.get("id", f"camera_{index}")).strip()
        if not camera_id or not CAMERA_ID_RE.fullmatch(camera_id):
            raise ValueError(
                f"ID de camera invalido: {camera_id!r}. Use apenas letras, numeros, _ e -."
            )
        if camera_id in seen_ids:
            raise ValueError(f"ID de camera duplicado: {camera_id}")
        seen_ids.add(camera_id)

        camera["id"] = camera_id
        camera["name"] = str(camera.get("name") or camera_id)
        camera["enabled"] = bool(camera.get("enabled", True))
        if camera["enabled"]:
            enabled_count += 1
        if "source" not in camera:
            raise ValueError(f"A camera {camera_id} precisa de video.cameras[].source")

        # Cada camera pode sobrescrever dimensoes, stride, ROI e gate.
        camera["width"] = int(camera.get("width", video.get("width", 640)))
        camera["height"] = int(camera.get("height", video.get("height", 480)))
        camera["fps"] = max(1, int(camera.get("fps", video.get("fps", 30))))
        camera["backend"] = str(camera.get("backend", video.get("backend", "auto"))).lower()
        camera["fourcc"] = str(camera.get("fourcc", video.get("fourcc", "MJPG"))).upper()
        camera["inference_fps"] = max(0.5, float(camera.get("inference_fps", video.get("inference_fps", 6.0))))
        camera["inference_stride"] = max(
            1, int(camera.get("inference_stride", video.get("inference_stride", 1)))
        )

        camera_roi = deepcopy(cfg["roi"])
        if isinstance(camera.get("roi"), dict):
            _merge(camera_roi, camera["roi"])
        _validate_roi(camera_roi, f"video.cameras[{camera_id}].roi")
        camera["roi"] = camera_roi

        camera_gate = deepcopy(cfg["gate"])
        if isinstance(camera.get("gate"), dict):
            _merge(camera_gate, camera["gate"])
        _validate_gate(camera_gate, f"video.cameras[{camera_id}].gate")
        camera["gate"] = camera_gate

        normalized_cameras.append(camera)

    if enabled_count < 1:
        raise ValueError("Pelo menos uma camera deve estar com enabled: true")

    video["cameras"] = normalized_cameras

    api_cfg = cfg.setdefault("api", {})
    auth_cfg = api_cfg.setdefault("auth", {})
    if bool(auth_cfg.get("enabled", True)) and not str(auth_cfg.get("api_key_env", "")).strip():
        raise ValueError("api.auth.api_key_env deve informar o nome da variavel de ambiente")

    jpeg_quality = int(api_cfg.get("jpeg_quality", 82))
    if not 40 <= jpeg_quality <= 100:
        raise ValueError("api.jpeg_quality deve ficar entre 40 e 100")
    api_cfg["jpeg_quality"] = jpeg_quality
    api_cfg["stream_fps"] = max(1, min(int(api_cfg.get("stream_fps", 10)), 30))

    display_cfg = cfg.setdefault("display", {})
    display_cfg["preview_fps"] = max(5, min(int(display_cfg.get("preview_fps", 20)), 60))
    display_cfg["max_box_age_ms"] = max(100, min(int(display_cfg.get("max_box_age_ms", 700)), 5000))

    perf_cfg = cfg.setdefault("performance", {})
    perf_cfg["max_concurrent_inferences"] = max(1, min(int(perf_cfg.get("max_concurrent_inferences", 1)), 8))
    perf_cfg["torch_threads"] = max(0, int(perf_cfg.get("torch_threads", 0)))
    perf_cfg["opencv_threads"] = max(0, int(perf_cfg.get("opencv_threads", 1)))

    return cfg


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


def resolve_tracker(value: str) -> str:
    local = BASE_DIR / value
    return str(local) if local.exists() else value
