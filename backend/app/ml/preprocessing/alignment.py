"""Face alignment for ArcFace.

Maps the 5 SCRFD landmarks onto the standard ArcFace 112x112 template with a similarity
transform (rotation + uniform scale + translation), the same geometry as
insightface/utils/face_align.py `norm_crop`. InsightFace estimates the transform with
skimage's SimilarityTransform (least squares, Umeyama); here the closed-form Umeyama
solution is computed directly with NumPy so the result is deterministic and dependency-free.

Output: 112x112x3 uint8 BGR. Pixel normalisation happens inside the recognizer.
"""
from __future__ import annotations

import cv2
import numpy as np

PREPROCESSING_VERSION = "arcface-5pt-umeyama-112-v1"

ARCFACE_TEMPLATE = np.array([
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
], dtype=np.float32)


def umeyama_similarity(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Least-squares similarity transform src -> dst (Umeyama 1991). Returns 2x3 matrix."""
    src = src.astype(np.float64)
    dst = dst.astype(np.float64)
    n = src.shape[0]
    mu_s, mu_d = src.mean(0), dst.mean(0)
    sc, dc = src - mu_s, dst - mu_d
    cov = dc.T @ sc / n
    u, s, vt = np.linalg.svd(cov)
    d = np.ones(2)
    if np.linalg.det(cov) < 0:
        d[-1] = -1
    r = u @ np.diag(d) @ vt
    var_s = (sc ** 2).sum() / n
    scale = (s * d).sum() / var_s
    t = mu_d - scale * r @ mu_s
    return np.hstack([scale * r, t[:, None]]).astype(np.float32)


class FaceAlignmentService:
    output_size = 112
    version = PREPROCESSING_VERSION

    def align(self, frame: np.ndarray, landmarks: np.ndarray) -> np.ndarray:
        if landmarks.shape != (5, 2) or not np.isfinite(landmarks).all():
            raise ValueError("landmarks must be a finite (5, 2) array")
        m = umeyama_similarity(landmarks, ARCFACE_TEMPLATE)
        return cv2.warpAffine(frame, m, (self.output_size, self.output_size), borderValue=0.0)
