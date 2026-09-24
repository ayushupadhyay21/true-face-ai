"""Runs the per-frame ML steps in the fixed pipeline order and records their latencies.

detect (exactly one face) -> passive liveness score -> alignment -> quality
-> [106 landmarks for eyes] -> [embedding]

Embeddings are computed only when asked for. They are never searched here: the
identity search happens after the session has passed liveness (see session_engine.py).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.ml.base import DetectedFace
from app.ml.preprocessing.landmarks106 import eyes_openness
from app.ml.quality.service import QualityResult
from app.ml.registry import ModelRegistry


@dataclass
class FrameAnalysis:
    face: DetectedFace | None
    face_count: int
    error: ErrorCode | None
    liveness_score: float | None = None
    quality: QualityResult | None = None
    eye_openness: float | None = None
    embedding: np.ndarray | None = None
    timings_ms: dict[str, float] = field(default_factory=dict)


def decode_frame(data: bytes, settings: Settings) -> np.ndarray:
    if not data or len(data) > settings.max_frame_bytes:
        raise AppError(ErrorCode.INVALID_FRAME, "Frame is empty or too large")
    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None or img.ndim != 3 or min(img.shape[:2]) < 64:
        raise AppError(ErrorCode.INVALID_FRAME, "Frame could not be decoded as an image")
    if max(img.shape[:2]) > settings.max_frame_side:
        raise AppError(ErrorCode.INVALID_FRAME, f"Frame larger than {settings.max_frame_side}px")
    return img


class FrameAnalyzer:
    def __init__(self, registry: ModelRegistry, settings: Settings):
        self.r = registry
        self.s = settings

    def analyze(self, frame: np.ndarray, *, require_frontal: bool, need_eyes: bool,
                need_embedding: bool) -> FrameAnalysis:
        t = {}
        t0 = time.perf_counter()
        det = self.r.detection.detect_single(frame)
        t["detection"] = (time.perf_counter() - t0) * 1000
        if det.face is None:
            return FrameAnalysis(None, det.face_count, det.error, timings_ms=t)
        face = det.face
        res = FrameAnalysis(face, 1, None, timings_ms=t)

        if face.size >= self.s.liveness_min_face_size:
            t0 = time.perf_counter()
            res.liveness_score = self.r.liveness.frame_score(frame, face)
            t["liveness"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        aligned = self.r.alignment.align(frame, face.landmarks)
        t["alignment"] = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        res.quality = self.r.quality.evaluate(face, aligned, require_frontal=require_frontal)
        t["quality"] = (time.perf_counter() - t0) * 1000
        if not res.quality.valid:
            res.error = ErrorCode.LOW_FACE_QUALITY
            return res

        if need_eyes:
            t0 = time.perf_counter()
            res.eye_openness = eyes_openness(self.r.landmarks106.predict(frame, face))
            t["landmarks106"] = (time.perf_counter() - t0) * 1000
        if need_embedding:
            t0 = time.perf_counter()
            res.embedding = self.r.embedding.embed_one(aligned)
            t["embedding"] = (time.perf_counter() - t0) * 1000
        return res
