"""Phase 40: per-stage latency, CPU and RAM of the pipeline on CPU.

Uses LFW images (single centred face crop) as input frames resized to 640x480, the
resolution the frontend sends. The DB vector search latency is measured only when
PostgreSQL is configured (synthetic gallery). GPU/VRAM: not applicable (no CUDA GPU).

Usage: python evaluation/performance/benchmark.py --n 100
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ROOT, hardware, new_experiment_id, save_experiment  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.ml.preprocessing.landmarks106 import eyes_openness  # noqa: E402
from app.ml.registry import get_registry  # noqa: E402


def pct(v: list[float], q: float) -> float:
    return float(np.percentile(v, q)) if v else float("nan")


def vector_search_latency(reg, n_people=200, per_person=5, queries=50) -> dict | None:
    s = get_settings()
    if not s.postgres_password:
        return None
    from app.db.database import Database, apply_migrations
    from app.db.repositories import EmbeddingMeta, PeopleRepository, VectorSearchService
    try:
        apply_migrations(s.database_url)
        db = Database(s.database_url)
        db.ping()
    except Exception as e:  # noqa: BLE001
        return {"skipped": str(e)}
    meta = EmbeddingMeta("benchmark_synthetic", "v0", 512, "bench")
    people, vec = PeopleRepository(db), VectorSearchService(db)
    rng = np.random.default_rng(0)
    ids = []
    for i in range(n_people):
        p = people.create(f"bench-{i}", None, "ACTIVE")
        ids.append(p["id"])
        for _ in range(per_person):
            v = rng.normal(size=512).astype(np.float32)
            vec.insert(p["id"], v / np.linalg.norm(v), meta)
    t = []
    for _ in range(queries):
        q = rng.normal(size=512).astype(np.float32)
        t0 = time.perf_counter()
        vec.search(q / np.linalg.norm(q), meta)
        t.append((time.perf_counter() - t0) * 1000)
    for pid in ids:
        people.delete(pid)
    return {"gallery_embeddings": n_people * per_person, "p50_ms": pct(t, 50), "p95_ms": pct(t, 95)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    args = ap.parse_args()
    reg = get_registry()
    paths = sorted((ROOT / "datasets" / "lfw" / "lfw").rglob("*.jpg"))[::50][: args.n]
    if not paths:
        sys.exit("LFW images not found")
    frames = []
    for p in paths:
        img = cv2.imread(str(p))[40:210, 40:210]
        canvas = np.full((480, 640, 3), 90, np.uint8)
        face = cv2.resize(img, (300, 300))
        canvas[90:390, 170:470] = face
        frames.append(canvas)

    proc = psutil.Process()
    proc.cpu_percent(None)
    stages = {k: [] for k in ("detection", "quality", "alignment", "liveness", "landmarks106", "embedding", "total")}
    for fr in frames[:5]:  # warm-up
        reg.detection.detect_single(fr)
    t_wall = time.perf_counter()
    for fr in frames:
        t_all = time.perf_counter()
        t0 = time.perf_counter()
        res = reg.detection.detect_single(fr)
        stages["detection"].append((time.perf_counter() - t0) * 1000)
        if res.face is None:
            continue
        t0 = time.perf_counter()
        aligned = reg.alignment.align(fr, res.face.landmarks)
        stages["alignment"].append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        reg.quality.evaluate(res.face, aligned)
        stages["quality"].append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        reg.liveness.frame_score(fr, res.face)
        stages["liveness"].append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        eyes_openness(reg.landmarks106.predict(fr, res.face))
        stages["landmarks106"].append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        reg.embedding.embed_one(aligned)
        stages["embedding"].append((time.perf_counter() - t0) * 1000)
        stages["total"].append((time.perf_counter() - t_all) * 1000)
    wall = time.perf_counter() - t_wall
    cpu = proc.cpu_percent(None) / psutil.cpu_count()
    rss = proc.memory_info().rss / 2**20

    vs = vector_search_latency(reg)
    exp_id = new_experiment_id("performance")
    date = datetime.now(timezone.utc).isoformat()
    table = {k: {"n": len(v), "mean_ms": statistics.fmean(v) if v else None, "p50_ms": pct(v, 50),
                 "p95_ms": pct(v, 95)} for k, v in stages.items()}
    fps_full = len(stages["total"]) / wall if wall else 0
    lines = [f"# Performance report ({exp_id})", "", f"Date: {date}", "",
             "Hardware: " + ", ".join(f"{k}={v}" for k, v in hardware().items()), "",
             f"Input: {len(frames)} synthetic 640x480 frames (LFW face crop pasted on grey canvas), CPU only.", "",
             "| stage | n | mean ms | p50 ms | p95 ms |", "|---|---|---|---|---|"]
    lines += [f"| {k} | {v['n']} | {v['mean_ms']:.1f} | {v['p50_ms']:.1f} | {v['p95_ms']:.1f} |"
              for k, v in table.items() if v["n"]]
    lines += ["", f"- Full per-frame pipeline throughput (all stages every frame): {fps_full:.2f} FPS",
              f"- Process CPU (average over run, % of all logical CPUs): {cpu:.0f}%",
              f"- Process RSS after run: {rss:.0f} MB",
              "- GPU / VRAM: not applicable (Intel UHD, no CUDA; ONNX Runtime CPUExecutionProvider)",
              f"- Vector search: {vs if vs else 'not measured (PostgreSQL not configured)'}", "",
              "In a live session not every stage runs on every frame (embedding only on passive/CENTER frames, "
              "106 landmarks only for baseline and BLINK), so session frame rate is higher than the full-pipeline figure."]
    report = ROOT / "evaluation" / "reports" / "performance_report.md"
    if report.exists():  # never overwrite: keep previous report under its own name
        report.rename(report.with_name(f"performance_report_{int(report.stat().st_mtime)}.md"))
    report.write_text("\n".join(lines), encoding="utf-8")
    save_experiment({"experiment_id": exp_id, "date": date, "model": reg.describe(), "model_version": "see model",
                     "dataset": f"LFW crops x{len(frames)}", "configuration": {"providers": get_settings().onnx_providers},
                     "threshold": None, "hardware": hardware(),
                     "metrics": {"stages": table, "fps_full_pipeline": fps_full, "cpu_percent": cpu, "rss_mb": rss,
                                 "vector_search": vs},
                     "results": {"report": str(report.relative_to(ROOT))}, "notes": ""})
    print("\n".join(lines))


if __name__ == "__main__":
    main()
