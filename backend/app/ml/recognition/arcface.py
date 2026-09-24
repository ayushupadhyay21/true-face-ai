"""ArcFace recognizer (InsightFace w600k_r50.onnx: ResNet-50 trained on WebFace600K).

Preprocessing matches insightface/model_zoo/arcface_onnx.py for non-MXNet exports:
BGR -> RGB, (x - 127.5) / 127.5, NCHW. The embedding dimension is read from the ONNX
graph, not assumed. Embeddings are L2-normalised so cosine similarity = dot product.
"""
from __future__ import annotations

import cv2
import numpy as np

from app.core.errors import AppError, ErrorCode
from app.ml.base import FaceRecognizer, ModelInfo
from app.ml.onnx_utils import create_session, file_sha256_prefix

INPUT_MEAN = 127.5
INPUT_STD = 127.5


class ArcFaceRecognizer(FaceRecognizer):
    def __init__(self, model_path, providers: str = "CPUExecutionProvider", threads: int = 0):
        self.session = create_session(model_path, providers, threads)
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        self.input_size = (int(inp.shape[3]), int(inp.shape[2]))
        dim = self.session.get_outputs()[0].shape[1]
        if not isinstance(dim, int):
            raise ValueError("Could not read embedding dimension from model graph")
        self.embedding_dimension = dim
        self.info = ModelInfo(name="arcface_w600k_r50", version=file_sha256_prefix(model_path),
                              extra={"file": model_path.name, "embedding_dimension": dim})

    def embed(self, aligned_faces: list[np.ndarray]) -> np.ndarray:
        if not aligned_faces:
            return np.zeros((0, self.embedding_dimension), dtype=np.float32)
        for f in aligned_faces:
            if f.shape[:2] != (self.input_size[1], self.input_size[0]):
                raise ValueError(f"aligned face must be {self.input_size}, got {f.shape[:2]}")
        # The exported graph has a fixed batch of 1 on the output, so run faces one at a time.
        out = []
        for face in aligned_faces:
            blob = cv2.dnn.blobFromImage(face, 1.0 / INPUT_STD, self.input_size,
                                         (INPUT_MEAN, INPUT_MEAN, INPUT_MEAN), swapRB=True)
            out.append(self.session.run(None, {self.input_name: blob})[0][0])
        emb = np.asarray(out, dtype=np.float32)
        norms = np.linalg.norm(emb, axis=1, keepdims=True)
        if not np.isfinite(emb).all() or (norms < 1e-6).any():
            raise AppError(ErrorCode.MODEL_UNAVAILABLE, "Embedding model produced an invalid output")
        return emb / norms


class FaceEmbeddingService:
    def __init__(self, recognizer: FaceRecognizer):
        self.recognizer = recognizer

    @property
    def info(self) -> ModelInfo:
        return self.recognizer.info

    def embed_one(self, aligned: np.ndarray) -> np.ndarray:
        return self.recognizer.embed([aligned])[0]

    @staticmethod
    def mean_embedding(embeddings: np.ndarray) -> np.ndarray:
        m = embeddings.mean(axis=0)
        return (m / np.linalg.norm(m)).astype(np.float32)
