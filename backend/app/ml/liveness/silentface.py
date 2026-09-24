"""Passive liveness with Silent-Face-Anti-Spoofing MiniFASNet models (Minivision, Apache-2.0).

Per frame, each model gets its own crop around the face box, as in upstream
generate_patches.CropImage: the box is enlarged by the scale in the model file name
(2.7 or 4.0), shifted to stay inside the image, and resized to 80x80. Input is BGR, raw
0..255 floats (upstream to_tensor does not divide by 255). Each ONNX model outputs a
3-class softmax (exported with training/scripts/export_silentface_onnx.py); class 1 = real.

Frame score = mean of the two models' class-1 probabilities. This is the upstream fusion:
test.py sums both softmax vectors and divides the winning entry by 2.

Temporal aggregation (predict): arithmetic mean of frame scores over N frames, compared
with the threshold. Rationale: score-level mean fusion is the same rule upstream uses to
combine models, and averaging reduces per-frame noise from blur and lighting.
It assumes errors are not strongly correlated across frames. A static spoof yields
correlated frames, so aggregation adds robustness to noise, not attack coverage.
Upstream detects boxes with its own RetinaFace-Caffe model; we use SCRFD boxes, which may
be slightly tighter. This domain shift is documented in MODEL_DOCUMENTATION.md.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.ml.base import DetectedFace, LivenessDetector, LivenessResult, ModelInfo
from app.ml.onnx_utils import create_session, file_sha256_prefix

REAL_CLASS = 1


def parse_model_name(stem: str) -> tuple[float | None, int, int]:
    """Mirror of upstream utility.parse_model_name: '2.7_80x80_MiniFASNetV2' -> (2.7, 80, 80);
    '4_0_0_80x80_MiniFASNetV1SE' -> (4.0, 80, 80)."""
    info = stem.split("_")[:-1]
    h, w = info[-1].split("x")
    scale = None if info[0] == "org" else float(info[0])
    return scale, int(h), int(w)


def crop_patch(frame: np.ndarray, bbox_xywh: tuple[float, float, float, float], scale: float | None,
               out_w: int, out_h: int) -> np.ndarray:
    """Port of upstream CropImage.crop / _get_new_box."""
    if scale is None:
        return cv2.resize(frame, (out_w, out_h))
    src_h, src_w = frame.shape[:2]
    x, y, box_w, box_h = bbox_xywh
    scale = min((src_h - 1) / box_h, min((src_w - 1) / box_w, scale))
    new_w, new_h = box_w * scale, box_h * scale
    cx, cy = box_w / 2 + x, box_h / 2 + y
    lx, ly, rx, ry = cx - new_w / 2, cy - new_h / 2, cx + new_w / 2, cy + new_h / 2
    if lx < 0:
        rx -= lx
        lx = 0
    if ly < 0:
        ry -= ly
        ly = 0
    if rx > src_w - 1:
        lx -= rx - src_w + 1
        rx = src_w - 1
    if ry > src_h - 1:
        ly -= ry - src_h + 1
        ry = src_h - 1
    lx, ly, rx, ry = int(lx), int(ly), int(rx), int(ry)
    return cv2.resize(frame[ly:ry + 1, lx:rx + 1], (out_w, out_h))


class SilentFaceLivenessDetector(LivenessDetector):
    def __init__(self, model_paths: list[Path], threshold: float = 0.5,
                 providers: str = "CPUExecutionProvider", threads: int = 0):
        if not model_paths:
            raise ValueError("at least one liveness model is required")
        self.models = []
        versions = []
        for p in model_paths:
            scale, h, w = parse_model_name(p.stem)
            sess = create_session(p, providers, threads)
            self.models.append((sess, sess.get_inputs()[0].name, scale, h, w))
            versions.append(file_sha256_prefix(p, 8))
        self.threshold = threshold
        self.info = ModelInfo(name="silentface_minifasnet_" + "+".join(p.stem.split("_")[-1] for p in model_paths),
                              version="-".join(versions))

    def frame_score(self, frame: np.ndarray, face: DetectedFace) -> float:
        x1, y1, x2, y2 = (float(v) for v in face.bbox)
        # upstream boxes are [left, top, w, h] with w = right - left + 1
        xywh = (x1, y1, x2 - x1 + 1, y2 - y1 + 1)
        probs = []
        for sess, name, scale, h, w in self.models:
            patch = crop_patch(frame, xywh, scale, w, h)
            x = patch.astype(np.float32).transpose(2, 0, 1)[None]
            probs.append(float(sess.run(None, {name: x})[0][0, REAL_CLASS]))
        return float(np.mean(probs))

    def predict(self, face_frames: list[tuple[np.ndarray, DetectedFace]]) -> LivenessResult:
        scores = [self.frame_score(f, face) for f, face in face_frames]
        return self.aggregate(scores)

    def aggregate(self, scores: list[float]) -> LivenessResult:
        score = float(np.mean(scores)) if scores else 0.0
        return LivenessResult(is_live=bool(scores) and score >= self.threshold, score=score,
                              frame_scores=[round(s, 4) for s in scores], model=self.info.name,
                              model_version=self.info.version, aggregation=f"mean_over_{len(scores)}_frames")
