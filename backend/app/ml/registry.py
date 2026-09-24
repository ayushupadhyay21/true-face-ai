"""Builds the model objects once per process from Settings."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import cv2

from app.core.config import Settings, get_settings
from app.ml.detection.scrfd import SCRFDDetector
from app.ml.detection.service import FaceDetectionService
from app.ml.liveness.silentface import SilentFaceLivenessDetector
from app.ml.preprocessing.alignment import FaceAlignmentService
from app.ml.preprocessing.landmarks106 import Landmark106
from app.ml.quality.service import FaceQualityService
from app.ml.recognition.arcface import ArcFaceRecognizer, FaceEmbeddingService


@dataclass
class ModelRegistry:
    detection: FaceDetectionService
    quality: FaceQualityService
    alignment: FaceAlignmentService
    embedding: FaceEmbeddingService
    liveness: SilentFaceLivenessDetector
    landmarks106: Landmark106

    def describe(self) -> dict:
        r = self.embedding.recognizer
        return {
            "detector": vars(self.detection.detector.info),
            "recognizer": {**vars(r.info), "embedding_dimension": r.embedding_dimension,
                           "preprocessing_version": self.alignment.version},
            "liveness": vars(self.liveness.info),
            "landmarks106": vars(self.landmarks106.info),
        }


def build_registry(settings: Settings) -> ModelRegistry:
    # OpenCV's own thread pool intermittently fails inside cv2.resize on the audit machine once
    # ONNX Runtime sessions are loaded ("Unknown C++ exception", reproduced 100/100 in one process,
    # 0/100 with one thread). The CV ops here are tiny next to ONNX inference, so run them single-threaded.
    cv2.setNumThreads(1)
    p, t = settings.onnx_providers, settings.onnx_threads
    detector = SCRFDDetector(settings.model_path(settings.detector_model), p, t, settings.det_input_size,
                             settings.det_score_threshold, settings.det_nms_threshold)
    recognizer = ArcFaceRecognizer(settings.model_path(settings.recognizer_model), p, t)
    liveness = SilentFaceLivenessDetector(
        [settings.model_path(m.strip()) for m in settings.liveness_models.split(",") if m.strip()],
        settings.liveness_threshold, p, t)
    return ModelRegistry(
        detection=FaceDetectionService(detector, settings.det_min_count_face_size),
        quality=FaceQualityService(settings),
        alignment=FaceAlignmentService(),
        embedding=FaceEmbeddingService(recognizer),
        liveness=liveness,
        landmarks106=Landmark106(settings.model_path(settings.landmark106_model), p, t),
    )


@lru_cache
def get_registry() -> ModelRegistry:
    return build_registry(get_settings())
