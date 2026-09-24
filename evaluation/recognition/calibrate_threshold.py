"""Phase 12: calibrate the identity threshold on LFW verification pairs.

Pipeline per image: SCRFD -> ArcFace alignment -> ArcFace embedding (same code as the app).
LFW images are 250x250 news photos that often contain background faces, so for this
OFFLINE dataset evaluation the face nearest the image centre is used (LFW's subject is
centred by construction). The live verification path never does this: it rejects 2+ faces.

Outputs:
  evaluation/recognition/threshold_config.json   (read by the backend)
  evaluation/reports/recognition/<experiment_id>/ (plots + report.md)
  evaluation/experiments/<experiment_id>.json     (experiment record, never overwritten)

Usage: python evaluation/recognition/calibrate_threshold.py --target-far 0.001
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ROOT, hardware, new_experiment_id, save_experiment  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.ml.registry import get_registry  # noqa: E402
from recognition.metrics import best_accuracy_threshold, eer, far_frr, threshold_at_far  # noqa: E402

LFW = ROOT / "datasets" / "lfw"
CACHE = ROOT / "evaluation" / "recognition" / "raw"


def read_pairs(path: Path) -> list[tuple[str, str, bool, int]]:
    lines = path.read_text().strip().splitlines()
    n_folds, n = map(int, lines[0].split())
    pairs = []
    for idx, line in enumerate(lines[1:]):
        fold = idx // (2 * n)
        p = line.split()
        if len(p) == 3:
            pairs.append((f"{p[0]}/{p[0]}_{int(p[1]):04d}.jpg", f"{p[0]}/{p[0]}_{int(p[2]):04d}.jpg", True, fold))
        else:
            pairs.append((f"{p[0]}/{p[0]}_{int(p[1]):04d}.jpg", f"{p[2]}/{p[2]}_{int(p[3]):04d}.jpg", False, fold))
    assert len(pairs) == n_folds * 2 * n
    return pairs


def embed_images(paths: list[str], reg) -> tuple[dict[str, np.ndarray], list[str]]:
    CACHE.mkdir(parents=True, exist_ok=True)
    rec = reg.embedding.recognizer
    cache_file = CACHE / f"lfw_{rec.info.name}_{rec.info.version}_{reg.alignment.version}.npz"
    if cache_file.exists():
        d = np.load(cache_file, allow_pickle=True)
        return dict(zip(d["paths"], d["emb"])), list(d["failed"])
    out, failed = {}, []
    t0 = time.time()
    for n, rel in enumerate(paths):
        img = cv2.imread(str(LFW / "lfw" / rel))
        faces = reg.detection.detector.detect(img) if img is not None else []
        if not faces:
            failed.append(rel)
            continue
        c = np.array(img.shape[1::-1]) / 2
        face = min(faces, key=lambda f: np.linalg.norm((f.bbox[:2] + f.bbox[2:]) / 2 - c))
        out[rel] = reg.embedding.embed_one(reg.alignment.align(img, face.landmarks))
        if n % 500 == 0:
            print(f"  {n}/{len(paths)} images, {time.time() - t0:.0f}s", flush=True)
    np.savez(cache_file, paths=np.array(list(out)), emb=np.array(list(out.values())), failed=np.array(failed))
    return out, failed


def plot(genuine, impostor, thr, out_dir: Path) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    files = []
    fig, ax = plt.subplots(figsize=(7, 4))
    bins = np.linspace(-0.3, 1.0, 131)
    ax.hist(impostor, bins, alpha=0.6, label=f"impostor (n={len(impostor)})", color="#c0504d")
    ax.hist(genuine, bins, alpha=0.6, label=f"genuine (n={len(genuine)})", color="#4f81bd")
    ax.axvline(thr, color="k", ls="--", label=f"threshold {thr:.3f}")
    ax.set_xlabel("cosine similarity"), ax.set_ylabel("pairs"), ax.legend(), ax.set_title("LFW similarity distributions")
    fig.tight_layout(), fig.savefig(out_dir / "similarity_hist.png", dpi=120), plt.close(fig)
    files.append("similarity_hist.png")

    t = np.linspace(-0.3, 1.0, 1301)
    far, frr = far_frr(genuine, impostor, t)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(t, far, label="FAR"), ax.plot(t, frr, label="FRR")
    ax.axvline(thr, color="k", ls="--", label="threshold")
    ax.set_yscale("log"), ax.set_ylim(1e-4, 1.01), ax.set_xlabel("threshold"), ax.set_ylabel("rate"), ax.legend()
    ax.set_title("FAR / FRR vs threshold")
    fig.tight_layout(), fig.savefig(out_dir / "far_frr_curve.png", dpi=120), plt.close(fig)
    files.append("far_frr_curve.png")

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot(np.clip(far, 1e-5, 1), 1 - frr)
    ax.set_xscale("log"), ax.set_xlim(1e-4, 1), ax.set_xlabel("FAR"), ax.set_ylabel("TAR"), ax.set_title("ROC (LFW)")
    ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout(), fig.savefig(out_dir / "roc.png", dpi=120), plt.close(fig)
    files.append("roc.png")
    return files


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-far", type=float, default=0.001)
    args = ap.parse_args()
    settings = get_settings()
    reg = get_registry()
    rec = reg.embedding.recognizer
    pairs = read_pairs(LFW / "pairs.txt")
    paths = sorted({p for a, b, _, _ in pairs for p in (a, b)})
    print(f"{len(pairs)} pairs, {len(paths)} unique images")
    t0 = time.time()
    emb, failed = embed_images(paths, reg)
    embed_seconds = time.time() - t0

    scores, labels, folds = [], [], []
    skipped = 0
    for a, b, same, fold in pairs:
        if a not in emb or b not in emb:
            skipped += 1
            continue
        scores.append(float(emb[a] @ emb[b])), labels.append(same), folds.append(fold)
    scores, labels, folds = np.array(scores), np.array(labels), np.array(folds)
    genuine, impostor = scores[labels], scores[~labels]

    # 10-fold: choose threshold on 9 folds, measure on the held-out fold (honest estimate).
    cv = []
    for f in range(10):
        tr, te = folds != f, folds == f
        t = threshold_at_far(scores[tr & ~labels], args.target_far)
        far, frr = far_frr(scores[te & labels], scores[te & ~labels], np.array([t]))
        cv.append({"fold": f, "threshold": t, "far": float(far[0]), "frr": float(frr[0])})

    thr = threshold_at_far(impostor, args.target_far)
    far, frr = far_frr(genuine, impostor, np.array([thr]))
    eer_v, eer_t = eer(genuine, impostor)
    acc, acc_t = best_accuracy_threshold(genuine, impostor)
    exp_id = new_experiment_id("recognition-calibration")
    out_dir = ROOT / "evaluation" / "reports" / "recognition" / exp_id
    out_dir.mkdir(parents=True, exist_ok=True)
    plots = plot(genuine, impostor, thr, out_dir)

    results = {
        "threshold": thr, "selection_rule": f"smallest threshold with FAR <= {args.target_far} on all impostor pairs",
        "far_at_threshold": float(far[0]), "frr_at_threshold": float(frr[0]), "tar_at_threshold": float(1 - frr[0]),
        "eer": eer_v, "eer_threshold": eer_t, "best_accuracy": acc, "best_accuracy_threshold": acc_t,
        "cv_10fold_mean_far": float(np.mean([c["far"] for c in cv])),
        "cv_10fold_mean_frr": float(np.mean([c["frr"] for c in cv])),
        "cv_10fold_threshold_std": float(np.std([c["threshold"] for c in cv])),
        "genuine_pairs": int(len(genuine)), "impostor_pairs": int(len(impostor)), "pairs_skipped": skipped,
        "images_without_face": len(failed),
        "genuine_mean": float(genuine.mean()), "genuine_std": float(genuine.std()),
        "impostor_mean": float(impostor.mean()), "impostor_std": float(impostor.std()),
        "impostor_max": float(impostor.max()), "genuine_min": float(genuine.min()),
    }
    date = datetime.now(timezone.utc).isoformat()
    config = {"model_name": rec.info.name, "model_version": rec.info.version,
              "embedding_dimension": rec.embedding_dimension, "preprocessing_version": reg.alignment.version,
              "metric": "cosine_similarity", "threshold": thr, "target_far": args.target_far,
              "dataset": "LFW (lfw.tgz, pairs.txt: 10 folds x 300 genuine + 300 impostor)",
              "experiment_id": exp_id, "date": date,
              "note": "Calibrated on LFW web photos; webcam conditions differ. Re-calibrate on local data."}
    (ROOT / "evaluation" / "recognition" / "threshold_config.json").write_text(json.dumps(config, indent=2))

    record = {"experiment_id": exp_id, "date": date, "model": rec.info.name, "model_version": rec.info.version,
              "dataset": config["dataset"], "configuration": {"target_far": args.target_far,
                                                             "det_threshold": settings.det_score_threshold,
                                                             "preprocessing_version": reg.alignment.version},
              "threshold": thr, "hardware": hardware(), "metrics": results, "cv_folds": cv,
              "results": {"plots": [str(out_dir.relative_to(ROOT) / p) for p in plots],
                          "embedding_seconds": round(embed_seconds, 1)},
              "notes": "Face nearest image centre used for LFW (offline dataset rule only)."}
    save_experiment(record)

    lines = [f"# Recognition threshold calibration: {exp_id}", "",
             f"- Date: {date}", f"- Model: {rec.info.name} (version {rec.info.version}, "
             f"dim {rec.embedding_dimension}, preprocessing {reg.alignment.version})",
             f"- Dataset: {config['dataset']}", f"- Pairs used: {len(genuine)} genuine, {len(impostor)} impostor "
             f"(skipped {skipped}; images without a detected face: {len(failed)})", "",
             "| metric | value |", "|---|---|"]
    lines += [f"| {k} | {v:.4f} |" if isinstance(v, float) else f"| {k} | {v} |" for k, v in results.items()
              if k != "selection_rule"]
    lines += ["", f"Selection rule: {results['selection_rule']}.", "",
              "10-fold cross-validation (threshold chosen on 9 folds, measured on the held-out fold):", "",
              "| fold | threshold | FAR | FRR |", "|---|---|---|---|"]
    lines += [f"| {c['fold']} | {c['threshold']:.4f} | {c['far']:.4f} | {c['frr']:.4f} |" for c in cv]
    lines += ["", *[f"![{p}]({p})" for p in plots], "",
              "Limitation: with 3000 impostor pairs, FAR can only be resolved to about 3.3e-4, and LFW "
              "photos are not webcam frames. Treat this threshold as a starting point."]
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(results, indent=2))
    print(f"report: {out_dir}")


if __name__ == "__main__":
    main()
