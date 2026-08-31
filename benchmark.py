from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

from config import load_config, resolve_tracker
from counting import GateCounter


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Benchmark de tracker + contagem")
    p.add_argument("--video", required=True)
    p.add_argument("--expected", type=int, default=None, help="Quantidade real esperada")
    p.add_argument("--trackers", nargs="+", default=["tracker_bytetrack.yaml", "fasttrack.yaml", "botsort.yaml"])
    p.add_argument("--model", default=None)
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--output", default="benchmark_results.csv")
    return p.parse_args()


def run_one(video: str, tracker: str, cfg: dict, model_path: str) -> dict:
    model = YOLO(model_path)
    counter = GateCounter(
        left_x=cfg["gate"]["left_x"],
        right_x=cfg["gate"]["right_x"],
        stable_frames=cfg["gate"]["stable_frames"],
        stale_after_frames=cfg["gate"]["stale_after_frames"],
    )
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise RuntimeError(f"Nao foi possivel abrir {video}")
    frames = 0
    count = 0
    returns = 0
    start = time.perf_counter()
    resolved = resolve_tracker(tracker)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frames += 1
            results = model.track(
                frame,
                persist=True,
                tracker=resolved,
                classes=cfg["model"]["classes"],
                conf=cfg["model"]["confidence"],
                imgsz=cfg["model"]["imgsz"],
                verbose=False,
            )
            if results and results[0].boxes is not None and results[0].boxes.id is not None:
                boxes = results[0].boxes
                for bbox, track_id, confidence in zip(
                    boxes.xyxy.cpu().tolist(),
                    boxes.id.int().cpu().tolist(),
                    boxes.conf.cpu().tolist(),
                ):
                    event = counter.update(track_id, bbox, frame.shape[1], confidence, frames)
                    if event:
                        if event["contabilizado"]:
                            count += 1
                        else:
                            returns += 1
            counter.cleanup(frames)
    finally:
        cap.release()
    elapsed = max(1e-9, time.perf_counter() - start)
    return {
        "tracker": tracker,
        "frames": frames,
        "elapsed_s": round(elapsed, 3),
        "fps": round(frames / elapsed, 2),
        "contado": count,
        "retornos": returns,
    }


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    model_path = args.model or cfg["model"]["path"]
    rows = []
    for tracker in args.trackers:
        print(f"Testando {tracker}...")
        row = run_one(args.video, tracker, cfg, model_path)
        if args.expected is not None:
            error = abs(row["contado"] - args.expected)
            row["esperado"] = args.expected
            row["erro_absoluto"] = error
            row["precisao_contagem_pct"] = round(max(0.0, 100.0 * (1 - error / max(1, args.expected))), 2)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))

    output = Path(args.output)
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Resultado salvo em {output}")


if __name__ == "__main__":
    main()
