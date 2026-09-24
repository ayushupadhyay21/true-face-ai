"""Face-count policy: 0 faces -> NO_FACE, 1 -> continue, 2+ -> MULTIPLE_FACES.

Never picks one face out of several. Detections below `min_count_face_size` are ignored
for counting (tiny background false positives), and that size is documented in config.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.core.errors import ErrorCode
from app.ml.base import DetectedFace, FaceDetector


@dataclass(frozen=True)
class SingleFaceResult:
    face: DetectedFace | None
    error: ErrorCode | None
    face_count: int


class FaceDetectionService:
    def __init__(self, detector: FaceDetector, min_count_face_size: int):
        self.detector = detector
        self.min_count_face_size = min_count_face_size

    def detect_single(self, frame: np.ndarray) -> SingleFaceResult:
        faces = [f for f in self.detector.detect(frame) if f.size >= self.min_count_face_size]
        if not faces:
            return SingleFaceResult(None, ErrorCode.NO_FACE, 0)
        if len(faces) > 1:
            return SingleFaceResult(None, ErrorCode.MULTIPLE_FACES, len(faces))
        return SingleFaceResult(faces[0], None, 1)
