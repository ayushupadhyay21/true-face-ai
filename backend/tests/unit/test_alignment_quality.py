import cv2
import numpy as np
import pytest

from app.core.config import Settings
from app.ml.base import DetectedFace
from app.ml.preprocessing.alignment import ARCFACE_TEMPLATE, FaceAlignmentService, umeyama_similarity
from app.ml.quality.service import FaceQualityService, pose_proxies


def test_umeyama_recovers_known_similarity():
    ang, s, t = np.deg2rad(17), 1.7, np.array([12.0, -5.0])
    r = np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]])
    src = ARCFACE_TEMPLATE.astype(np.float64)
    dst = (s * src @ r.T) + t
    m = umeyama_similarity(src, dst)
    assert np.allclose(m[:, :2], s * r, atol=1e-4)
    assert np.allclose(m[:, 2], t, atol=1e-3)


def test_template_landmarks_map_to_identity():
    m = umeyama_similarity(ARCFACE_TEMPLATE, ARCFACE_TEMPLATE)
    assert np.allclose(m, [[1, 0, 0], [0, 1, 0]], atol=1e-5)


def test_align_output_deterministic_and_sized(registry, face_img):
    face = registry.detection.detect_single(face_img).face
    a1 = registry.alignment.align(face_img, face.landmarks)
    a2 = registry.alignment.align(face_img, face.landmarks)
    assert a1.shape == (112, 112, 3) and a1.dtype == np.uint8
    assert np.array_equal(a1, a2)


def test_alignment_undoes_rotation(registry, face_img):
    """Rotating the input 20 degrees must give almost the same aligned crop."""
    h, w = face_img.shape[:2]
    rot = cv2.warpAffine(face_img, cv2.getRotationMatrix2D((w / 2, h / 2), 20, 1.0), (w, h))
    f0 = registry.detection.detect_single(face_img).face
    f1 = registry.detection.detect_single(rot).face
    e0 = registry.embedding.embed_one(registry.alignment.align(face_img, f0.landmarks))
    e1 = registry.embedding.embed_one(registry.alignment.align(rot, f1.landmarks))
    assert float(e0 @ e1) > 0.8


def test_align_rejects_bad_landmarks():
    with pytest.raises(ValueError):
        FaceAlignmentService().align(np.zeros((100, 100, 3), np.uint8), np.full((5, 2), np.nan, np.float32))


def _quality(registry, img, **overrides):
    s = Settings(**overrides)
    face = registry.detection.detect_single(img).face
    return FaceQualityService(s).evaluate(face, registry.alignment.align(img, face.landmarks))


def test_good_face_passes_quality(registry, face_img):
    q = _quality(registry, cv2.resize(face_img, None, fx=1.5, fy=1.5))
    assert q.valid, q
    assert q.quality_reason is None


def test_blur_rejected(registry, face_img):
    img = cv2.GaussianBlur(cv2.resize(face_img, None, fx=1.5, fy=1.5), (0, 0), 6)
    q = _quality(registry, img)
    assert not q.valid and q.quality_reason == "TOO_BLURRY"


def test_dark_rejected(registry, face_img):
    img = (cv2.resize(face_img, None, fx=1.5, fy=1.5).astype(np.float32) * 0.2).astype(np.uint8)
    q = _quality(registry, img)
    assert not q.valid and q.quality_reason in ("TOO_DARK", "LOW_CONTRAST", "LOW_DETECTION_CONFIDENCE")


def test_small_face_rejected(registry, face_img):
    small = cv2.resize(face_img, None, fx=0.6, fy=0.6)
    canvas = np.full((300, 300, 3), 127, np.uint8)
    canvas[100:100 + small.shape[0], 100:100 + small.shape[1]] = small
    q = _quality(registry, canvas)
    assert not q.valid and q.quality_reason == "FACE_TOO_SMALL"


def test_thresholds_are_configurable(registry, face_img):
    q = _quality(registry, cv2.resize(face_img, None, fx=1.5, fy=1.5), quality_min_blur=1e9)
    assert q.quality_reason == "TOO_BLURRY"


def test_pose_proxies_frontal_and_turned():
    lm = ARCFACE_TEMPLATE.copy()
    yaw, pitch = pose_proxies(lm)
    assert abs(yaw) < 0.05 and abs(pitch) < 1e-6
    turned = lm.copy()
    turned[2, 0] += 15  # nose moves to image right
    assert pose_proxies(turned)[0] > 0.3
    face = DetectedFace(np.array([0, 0, 112, 112], np.float32), turned, 0.9)
    assert face.size == 112
