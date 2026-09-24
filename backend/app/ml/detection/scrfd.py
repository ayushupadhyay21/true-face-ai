"""SCRFD face detector (InsightFace det_10g.onnx), ONNX Runtime, CPU.

Decoding follows insightface/python-package/insightface/model_zoo/scrfd.py (MIT code):
3 feature strides (8, 16, 32), 2 anchors per location, outputs ordered
[scores x3, bbox distances x3, keypoints x3]. Input: RGB, (x - 127.5) / 128, letterboxed
into a square canvas (image pasted at top-left).
"""
from __future__ import annotations

import cv2
import numpy as np

from app.ml.base import DetectedFace, FaceDetector, ModelInfo
from app.ml.onnx_utils import create_session, file_sha256_prefix

STRIDES = (8, 16, 32)
NUM_ANCHORS = 2
INPUT_MEAN = 127.5
INPUT_STD = 128.0


def nms(boxes: np.ndarray, scores: np.ndarray, thresh: float) -> list[int]:
    x1, y1, x2, y2 = boxes.T
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0.0, xx2 - xx1 + 1) * np.maximum(0.0, yy2 - yy1 + 1)
        iou = inter / (areas[i] + areas[order[1:]] - inter)
        order = order[np.where(iou <= thresh)[0] + 1]
    return keep


class SCRFDDetector(FaceDetector):
    def __init__(self, model_path, providers: str = "CPUExecutionProvider", threads: int = 0,
                 input_size: int = 640, score_threshold: float = 0.5, nms_threshold: float = 0.4):
        self.session = create_session(model_path, providers, threads)
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]
        if len(self.output_names) != 9:
            raise ValueError(f"Unexpected SCRFD output count {len(self.output_names)} (expected 9 with keypoints)")
        self.input_size = input_size
        self.score_threshold = score_threshold
        self.nms_threshold = nms_threshold
        self.info = ModelInfo(name="scrfd_10g_bnkps", version=file_sha256_prefix(model_path),
                              extra={"file": model_path.name, "input_size": input_size})
        self._centers: dict[tuple[int, int, int], np.ndarray] = {}

    def _anchor_centers(self, h: int, w: int, stride: int) -> np.ndarray:
        key = (h, w, stride)
        if key not in self._centers:
            centers = np.stack(np.mgrid[:h, :w][::-1], axis=-1).astype(np.float32)
            centers = (centers * stride).reshape(-1, 2)
            centers = np.repeat(centers, NUM_ANCHORS, axis=0)
            self._centers[key] = centers
        return self._centers[key]

    def detect(self, frame: np.ndarray) -> list[DetectedFace]:
        if frame is None or frame.ndim != 3 or frame.shape[2] != 3 or frame.size == 0:
            raise ValueError("frame must be a non-empty HxWx3 BGR image")
        size = self.input_size
        h, w = frame.shape[:2]
        scale = size / max(h, w)
        nh, nw = int(round(h * scale)), int(round(w * scale))
        canvas = np.zeros((size, size, 3), dtype=np.uint8)
        canvas[:nh, :nw] = cv2.resize(frame, (nw, nh))
        blob = cv2.dnn.blobFromImage(canvas, 1.0 / INPUT_STD, (size, size),
                                     (INPUT_MEAN, INPUT_MEAN, INPUT_MEAN), swapRB=True)
        outs = self.session.run(self.output_names, {self.input_name: blob})

        all_scores, all_boxes, all_kps = [], [], []
        for idx, stride in enumerate(STRIDES):
            scores = outs[idx].reshape(-1)
            dist = outs[idx + 3].reshape(-1, 4) * stride
            kps = outs[idx + 6].reshape(-1, 10) * stride
            fh, fw = size // stride, size // stride
            centers = self._anchor_centers(fh, fw, stride)
            pos = np.where(scores >= self.score_threshold)[0]
            if pos.size == 0:
                continue
            c = centers[pos]
            d = dist[pos]
            boxes = np.stack([c[:, 0] - d[:, 0], c[:, 1] - d[:, 1], c[:, 0] + d[:, 2], c[:, 1] + d[:, 3]], axis=1)
            k = kps[pos].reshape(-1, 5, 2) + c[:, None, :]
            all_scores.append(scores[pos])
            all_boxes.append(boxes)
            all_kps.append(k)

        if not all_scores:
            return []
        scores = np.concatenate(all_scores)
        boxes = np.concatenate(all_boxes) / scale
        kps = np.concatenate(all_kps) / scale
        keep = nms(boxes, scores, self.nms_threshold)

        faces = []
        for i in keep:
            b = boxes[i].copy()
            b[[0, 2]] = np.clip(b[[0, 2]], 0, w - 1)
            b[[1, 3]] = np.clip(b[[1, 3]], 0, h - 1)
            faces.append(DetectedFace(bbox=b.astype(np.float32), landmarks=kps[i].astype(np.float32),
                                      confidence=float(scores[i])))
        faces.sort(key=lambda f: f.confidence, reverse=True)
        return faces
