"""Face quality checks. All thresholds come from Settings (see core/config.py).

Pose proxies (dimensionless, computed from the 5 SCRFD landmarks):
  yaw   = (nose_x - eye_mid_x) / inter_ocular_distance     (0 = frontal; sign = image direction)
  pitch = (nose_y - eye_mid_y) / (mouth_mid_y - eye_mid_y) - PITCH_NEUTRAL
These are geometric ratios, not angles in degrees. PITCH_NEUTRAL is the ratio for a frontal
face on the ArcFace template (nose sits ~49% of the way from eyes to mouth there).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import cv2
import numpy as np

from app.core.config import Settings
from app.ml.base import DetectedFace
from app.ml.preprocessing.alignment import ARCFACE_TEMPLATE

_t = ARCFACE_TEMPLATE
PITCH_NEUTRAL = float((_t[2, 1] - (_t[0, 1] + _t[1, 1]) / 2) / ((_t[3, 1] + _t[4, 1]) / 2 - (_t[0, 1] + _t[1, 1]) / 2))


def pose_proxies(landmarks: np.ndarray) -> tuple[float, float]:
    le, re, nose, lm, rm = landmarks
    eye_mid = (le + re) / 2
    mouth_mid = (lm + rm) / 2
    iod = float(np.linalg.norm(re - le))
    vert = float(mouth_mid[1] - eye_mid[1])
    if iod < 1e-6 or vert < 1e-6:
        return float("inf"), float("inf")
    yaw = float(nose[0] - eye_mid[0]) / iod
    pitch = float(nose[1] - eye_mid[1]) / vert - PITCH_NEUTRAL
    return yaw, pitch


@dataclass
class QualityResult:
    valid: bool
    face_size: float
    det_score: float
    blur_score: float
    brightness_score: float
    contrast_score: float
    yaw: float
    pitch: float
    landmarks_outside: float
    quality_reason: str | None

    def to_dict(self) -> dict:
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in asdict(self).items()}


class FaceQualityService:
    def __init__(self, settings: Settings):
        self.s = settings

    def evaluate(self, face: DetectedFace, aligned: np.ndarray, require_frontal: bool = True) -> QualityResult:
        gray = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
        blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        brightness = float(gray.mean())
        contrast = float(gray.std())
        yaw, pitch = pose_proxies(face.landmarks)
        x1, y1, x2, y2 = face.bbox
        lm = face.landmarks
        outside = float(np.mean((lm[:, 0] < x1) | (lm[:, 0] > x2) | (lm[:, 1] < y1) | (lm[:, 1] > y2)))

        s = self.s
        reason = None
        if face.size < s.quality_min_face_size:
            reason = "FACE_TOO_SMALL"
        elif face.confidence < s.quality_min_det_score:
            reason = "LOW_DETECTION_CONFIDENCE"
        elif outside > s.quality_max_landmark_outside:
            reason = "LANDMARKS_OUTSIDE_FACE"
        elif brightness < s.quality_min_brightness:
            reason = "TOO_DARK"
        elif brightness > s.quality_max_brightness:
            reason = "TOO_BRIGHT"
        elif contrast < s.quality_min_contrast:
            reason = "LOW_CONTRAST"
        elif blur < s.quality_min_blur:
            reason = "TOO_BLURRY"
        elif require_frontal and (abs(yaw) > s.quality_max_yaw or abs(pitch) > s.quality_max_pitch):
            reason = "NOT_FRONTAL"
        return QualityResult(valid=reason is None, face_size=face.size, det_score=face.confidence,
                             blur_score=blur, brightness_score=brightness, contrast_score=contrast,
                             yaw=yaw, pitch=pitch, landmarks_outside=outside, quality_reason=reason)
