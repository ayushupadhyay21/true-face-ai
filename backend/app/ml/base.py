"""Model-agnostic interfaces and data types.

Concrete models (SCRFD, ArcFace, Silent-Face) implement these, so experiments can swap
a model without touching services.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class DetectedFace:
    bbox: np.ndarray  # (4,) float32: x1, y1, x2, y2 in frame pixels
    landmarks: np.ndarray  # (5, 2) float32: left eye, right eye, nose, left mouth, right mouth (image left/right)
    confidence: float

    @property
    def width(self) -> float:
        return float(self.bbox[2] - self.bbox[0])

    @property
    def height(self) -> float:
        return float(self.bbox[3] - self.bbox[1])

    @property
    def size(self) -> float:
        return min(self.width, self.height)


@dataclass(frozen=True)
class ModelInfo:
    name: str
    version: str
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class LivenessResult:
    is_live: bool
    score: float  # aggregated probability of the "real face" class, 0..1
    frame_scores: list[float]
    model: str
    model_version: str
    aggregation: str


class FaceDetector(ABC):
    info: ModelInfo

    @abstractmethod
    def detect(self, frame: np.ndarray) -> list[DetectedFace]:
        """Return all faces in a BGR uint8 frame, highest confidence first."""


class FaceRecognizer(ABC):
    info: ModelInfo
    embedding_dimension: int
    input_size: tuple[int, int]

    @abstractmethod
    def embed(self, aligned_faces: list[np.ndarray]) -> np.ndarray:
        """Aligned BGR faces -> (N, D) float32 L2-normalised embeddings."""


class LivenessDetector(ABC):
    info: ModelInfo

    @abstractmethod
    def frame_score(self, frame: np.ndarray, face: DetectedFace) -> float:
        """Probability that this single face observation is a bona fide (live) face."""

    @abstractmethod
    def predict(self, face_frames: list[tuple[np.ndarray, DetectedFace]]) -> LivenessResult:
        """Aggregate a sequence of (frame, face) observations into one decision."""
