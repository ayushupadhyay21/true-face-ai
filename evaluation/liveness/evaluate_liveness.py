"""Phase 15: evaluate passive liveness (PAD) on locally recorded clips and fill the attack matrix.

Input: datasets/liveness/<CATEGORY>/*.mp4|*.avi|*.jpg|*.png and optional metadata.csv
(written by scripts/record_sample.py). This data is never used for training (the
Silent-Face weights are used as released), so there is no train/test overlap.

Per sample, the app's passive-phase rule is applied: the first N frames with exactly one
face (N = LIVENESS_MIN_FRAMES) are scored and their mean is compared with LIVENESS_THRESHOLD.
Samples with no usable face are reported separately, not counted as correct rejections.

Outputs evaluation/reports/liveness/<experiment_id>/{report.md, attack_matrix.md, samples.csv}
and evaluation/experiments/<experiment_id>.json.

Usage: python evaluation/liveness/evaluate_liveness.py [--frame-step 3]
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ROOT, hardware, new_experiment_id, save_experiment  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.ml.registry import get_registry  # noqa: E402
from liveness.pad_metrics import pad_metrics  # noqa: E402

DATA = ROOT / "datasets" / "liveness"
VIDEO = {".mp4", ".avi", ".mov", ".webm"}
IMAGE = {".jpg", ".jpeg", ".png"}
EXPECTED = ["BONA_FIDE", "PRINT_ATTACK", "PHONE_PHOTO", "PHONE_VIDEO", "LAPTOP_PHOTO", "LAPTOP_VIDEO",
            "MONITOR_PHOTO", "MONITOR_VIDEO", "TABLET_PHOTO", "TABLET_VIDEO"]


def frames_of(path: Path, step: int):
    if path.suffix.lower() in IMAGE:
        img = cv2.imread(str(path))
        if img is not None:
            yield img
        return
    cap = cv2.VideoCapture(str(path))
    i = 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if i % step == 0:
            yield f
        i += 1
    cap.release()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame-step", type=int, default=3)
    args = ap.parse_args()
    s = get_settings()
    reg = get_registry()
    meta = {}
    if (DATA / "metadata.csv").exists():
        with (DATA / "metadata.csv").open(encoding="utf-8") as f:
            meta = {r["file"]: r for r in csv.DictReader(f)}

    files = sorted(p for p in DATA.rglob("*") if p.suffix.lower() in VIDEO | IMAGE and p.parent != DATA)
    if not files:
        sys.exit(f"No samples under {DATA}. Record some with scripts/record_sample.py (see EVALUATION.md).")

    rows, scored = [], []
    for p in files:
        cat = p.parent.name
        rel = p.relative_to(DATA).as_posix()
        scores, multi, h, w = [], 0, None, None
        for fr in frames_of(p, args.frame_step):
            h, w = fr.shape[:2]
            res = reg.detection.detect_single(fr)
            if res.face is None:
                multi += res.face_count > 1
                continue
            if res.face.size < s.liveness_min_face_size:
                continue
            scores.append(reg.liveness.frame_score(fr, res.face))
            if len(scores) >= s.liveness_min_frames:
                break
        m = meta.get(rel, {})
        if len(scores) < (1 if p.suffix.lower() in IMAGE else s.liveness_min_frames):
            decision, agg = "NO_USABLE_FACE", None
        else:
            r = reg.liveness.aggregate(scores)
            decision, agg = ("LIVE" if r.is_live else "SPOOF"), r.score
            scored.append({"category": cat, "is_live": r.is_live})
        rows.append({"file": rel, "category": cat, "device": m.get("device", ""),
                     "resolution": m.get("resolution", "") or (f"{w}x{h} (capture)" if w else ""),
                     "lighting": m.get("lighting", ""), "subject": m.get("subject", ""),
                     "frames_scored": len(scores), "multi_face_frames": multi,
                     "liveness_score": round(agg, 4) if agg is not None else None,
                     "frame_scores": " ".join(f"{x:.3f}" for x in scores), "decision": decision,
                     "expected": "LIVE" if cat == "BONA_FIDE" else "SPOOF",
                     "notes": m.get("notes", "")})
        print(f"{rel}: {decision} {agg}")

    metrics = pad_metrics(scored)
    exp_id = new_experiment_id("liveness-eval")
    out = ROOT / "evaluation" / "reports" / "liveness" / exp_id
    out.mkdir(parents=True, exist_ok=True)
    with (out / "samples.csv").open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)

    date = datetime.now(timezone.utc).isoformat()
    tested = sorted({r["category"] for r in rows})
    lines = [f"# Attack test matrix: {exp_id}", "", f"Date: {date}. Passive PAD only (model {reg.liveness.info.name} "
             f"{reg.liveness.info.version}, threshold {s.liveness_threshold}, mean over {s.liveness_min_frames} frames).",
             "Recognition result column: not applicable here (PAD evaluation runs without identity search).", "",
             "| attack_type | device | resolution | lighting | expected | result | liveness_score | recognition_result | notes |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        result = "PASS" if r["decision"] == "LIVE" else ("REJECT" if r["decision"] == "SPOOF" else r["decision"])
        lines.append(f"| {r['category']} | {r['device']} | {r['resolution']} | {r['lighting']} | "
                     f"{'PASS' if r['expected'] == 'LIVE' else 'REJECT'} | {result} | {r['liveness_score']} | n/a | "
                     f"{r['notes']} |")
    lines += ["", "Categories NOT tested in this run: " + (", ".join(c for c in EXPECTED if c not in tested) or "none")]
    (out / "attack_matrix.md").write_text("\n".join(lines), encoding="utf-8")

    rep = [f"# Liveness evaluation {exp_id}", "", "```", *(f"{k}: {v}" for k, v in metrics.items()
                                                     if k != "APCER_per_species"), "```", "",
           "| species | n | accepted as live | APCER |", "|---|---|---|---|"]
    rep += [f"| {k} | {v['n']} | {v['accepted_as_live']} | {v['apcer']:.3f} |"
            for k, v in metrics["APCER_per_species"].items()]
    rep += ["", f"Samples without a usable face: {sum(r['decision'] == 'NO_USABLE_FACE' for r in rows)}",
            "", "Small local sample sizes give wide confidence intervals; do not generalise."]
    (out / "report.md").write_text("\n".join(rep), encoding="utf-8")

    save_experiment({"experiment_id": exp_id, "date": date, "model": reg.liveness.info.name,
                     "model_version": reg.liveness.info.version, "dataset": f"local recordings ({len(rows)} samples)",
                     "configuration": {"threshold": s.liveness_threshold, "min_frames": s.liveness_min_frames,
                                       "frame_step": args.frame_step},
                     "threshold": s.liveness_threshold, "hardware": hardware(), "metrics": metrics,
                     "results": {"report": str(out.relative_to(ROOT))}, "notes": "passive PAD only"})
    print(f"report: {out}")
    print({k: v for k, v in metrics.items() if k != "APCER_per_species"})


if __name__ == "__main__":
    main()
