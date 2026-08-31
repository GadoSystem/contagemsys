from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from benchmark import run_one
from config import load_config


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Executa benchmark em todos os videos com ground truth")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--ground-truth", default="tests/ground_truth.json")
    p.add_argument("--videos-dir", default="tests/videos")
    p.add_argument("--trackers", nargs="+", default=["tracker_bytetrack.yaml", "fasttrack.yaml", "botsort.yaml"])
    p.add_argument("--output", default="benchmark_suite_results.csv")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    gt_path = Path(args.ground_truth)
    data = json.loads(gt_path.read_text(encoding="utf-8"))
    truth = {k: v for k, v in data.items() if isinstance(v, int)}
    rows = []

    for video_name, expected in truth.items():
        video = Path(args.videos_dir) / video_name
        if not video.exists():
            print(f"Ignorando {video_name}: arquivo nao encontrado")
            continue
        for tracker in args.trackers:
            row = run_one(str(video), tracker, cfg, cfg["model"]["path"])
            error = abs(row["contado"] - expected)
            row.update({
                "video": video_name,
                "esperado": expected,
                "erro_absoluto": error,
                "precisao_contagem_pct": round(max(0.0, 100.0 * (1 - error / max(1, expected))), 2),
            })
            rows.append(row)
            print(row)

    if not rows:
        print("Nenhum video de benchmark encontrado. Coloque arquivos em tests/videos/.")
        return

    output = Path(args.output)
    fields = ["video", "tracker", "esperado", "contado", "erro_absoluto", "precisao_contagem_pct", "retornos", "frames", "elapsed_s", "fps"]
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Benchmark completo salvo em: {output}")


if __name__ == "__main__":
    main()
