"""106-point landmark model (InsightFace 2d106det.onnx), used only for eye openness (blink).

Preprocessing follows insightface/model_zoo/landmark.py: crop centred on the face box,
scale = 192 / (1.5 * max(w, h)), RGB, no mean/std (the graph starts with Sub/Mul nodes
that normalise internally). Output: 106 (x, y) in [-1, 1], mapped back with the inverse
affine transform.
"""
from __future__ import annotations

import cv2
import numpy as np

from app.ml.base import DetectedFace, ModelInfo
from app.ml.onnx_utils import create_session, file_sha256_prefix

# Eye contour indices of the 106-point markup. Established empirically by
# scripts/find_eye_indices.py (points nearest to the SCRFD eye centres); see MODEL_DOCUMENTATION.md.
LEFT_EYE_IDX = tuple(range(33, 43))  # image-left eye (subject's right eye)
RIGHT_EYE_IDX = tuple(range(87, 97))  # image-right eye (subject's left eye)


class Landmark106:
    def __init__(self, model_path, providers: str = "CPUExecutionProvider", threads: int = 0):
        self.session = create_session(model_path, providers, threads)
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        self.size = int(inp.shape[2])
        self.info = ModelInfo(name="insightface_2d106det", version=file_sha256_prefix(model_path))

    def predict(self, frame: np.ndarray, face: DetectedFace) -> np.ndarray:
        x1, y1, x2, y2 = face.bbox
        w, h = x2 - x1, y2 - y1
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        s = self.size / (max(w, h) * 1.5)
        m = np.array([[s, 0, self.size / 2 - s * cx], [0, s, self.size / 2 - s * cy]], dtype=np.float32)
        crop = cv2.warpAffine(frame, m, (self.size, self.size), borderValue=0.0)
        blob = cv2.dnn.blobFromImage(crop, 1.0, (self.size, self.size), (0, 0, 0), swapRB=True)
        pred = self.session.run(None, {self.input_name: blob})[0].reshape(-1, 2)
        pred = (pred + 1.0) * (self.size / 2)
        im = cv2.invertAffineTransform(m)
        return (pred @ im[:, :2].T + im[:, 2]).astype(np.float32)


def eye_openness(points: np.ndarray, idx: tuple[int, ...]) -> float:
    """Minor/major extent ratio of one eye contour (PCA), ~0.3-0.45 open, drops when closed.

    Scale- and rotation-invariant, and independent of the exact point ordering, so it does not
    rely on undocumented index pairs (unlike the 6-point EAR of Soukupova & Cech 2016, which
    this generalises).
    """
    p = points[list(idx)]
    p = p - p.mean(0)
    s = np.linalg.svd(p, compute_uv=False)
    return float(s[1] / s[0]) if s[0] > 1e-6 else 0.0


def eyes_openness(points: np.ndarray) -> float:
    return (eye_openness(points, LEFT_EYE_IDX) + eye_openness(points, RIGHT_EYE_IDX)) / 2
