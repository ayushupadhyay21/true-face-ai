"""Find which 2d106det landmark indices form each eye contour.

For every image, runs SCRFD + 2d106det and records the 10 landmark indices closest to
each SCRFD eye keypoint (normalised by inter-ocular distance). Prints how often each index
appears, so the eye index sets in app/ml/preprocessing/landmarks106.py are data-backed.

Usage: python scripts/find_eye_indices.py datasets/lfw/lfw --limit 200
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.ml.registry import get_registry  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("image_dir", type=Path)
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()
    reg = get_registry()
    left, right = Counter(), Counter()
    n = 0
    for path in sorted(args.image_dir.rglob("*.jpg"))[::13]:
        img = cv2.imread(str(path))
        res = reg.detection.detect_single(img)
        if res.face is None:
            continue
        pts = reg.landmarks106.predict(img, res.face)
        kps = res.face.landmarks
        for eye, counter in ((kps[0], left), (kps[1], right)):
            d = np.linalg.norm(pts - eye, axis=1)
            counter.update(np.argsort(d)[:10].tolist())
        n += 1
        if n >= args.limit:
            break
    print(f"images used: {n}")
    for label, c in (("image-left eye", left), ("image-right eye", right)):
        top = sorted(i for i, _ in c.most_common(10))
        print(f"{label}: top-10 indices {top}; hit rate of 10th: {c.most_common(10)[-1][1] / n:.2f}")


if __name__ == "__main__":
    main()
