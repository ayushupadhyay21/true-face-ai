import cv2
import numpy as np

from app.core.errors import ErrorCode
from app.ml.detection.scrfd import nms


def test_single_face_detected_with_landmarks_inside_box(registry, face_img):
    res = registry.detection.detect_single(face_img)
    assert res.error is None and res.face_count == 1
    f = res.face
    assert f.confidence > 0.5
    x1, y1, x2, y2 = f.bbox
    assert (f.landmarks[:, 0] >= x1).all() and (f.landmarks[:, 0] <= x2).all()
    assert (f.landmarks[:, 1] >= y1).all() and (f.landmarks[:, 1] <= y2).all()
    # eyes above nose above mouth (upright face)
    assert f.landmarks[:2, 1].max() < f.landmarks[2, 1] < f.landmarks[3:, 1].min()


def test_no_face_on_blank_and_noise(registry):
    blank = np.full((480, 640, 3), 127, np.uint8)
    noise = np.random.default_rng(0).integers(0, 255, (480, 640, 3), dtype=np.uint8)
    assert registry.detection.detect_single(blank).error == ErrorCode.NO_FACE
    assert registry.detection.detect_single(noise).error == ErrorCode.NO_FACE


def test_multiple_faces_rejected_not_selected(registry, lfw):
    a = lfw("Colin_Powell", 1)[40:210, 40:210]
    b = lfw("George_W_Bush", 1)[40:210, 40:210]
    pair = np.hstack([a, b])
    res = registry.detection.detect_single(pair)
    assert res.error == ErrorCode.MULTIPLE_FACES
    assert res.face is None and res.face_count == 2


def test_extremely_dark_image_gives_no_usable_face(registry, face_img):
    dark = (face_img.astype(np.float32) * 0.02).astype(np.uint8)
    res = registry.detection.detect_single(dark)
    if res.face is not None:  # detector may still fire; quality must then reject
        aligned = registry.alignment.align(dark, res.face.landmarks)
        assert not registry.quality.evaluate(res.face, aligned).valid


def test_partial_face_not_accepted_as_good_quality(registry, face_img):
    h, w = face_img.shape[:2]
    partial = face_img.copy()
    partial[:, : w // 2] = 0  # left half of the face missing
    res = registry.detection.detect_single(partial)
    if res.face is not None:
        aligned = registry.alignment.align(partial, res.face.landmarks)
        assert not registry.quality.evaluate(res.face, aligned).valid


def test_detection_scale_invariance(registry, face_img):
    big = cv2.resize(face_img, None, fx=2.5, fy=2.5)
    res = registry.detection.detect_single(big)
    assert res.error is None
    assert res.face.width > 150


def test_nms_suppresses_overlaps():
    boxes = np.array([[0, 0, 10, 10], [1, 1, 11, 11], [50, 50, 60, 60]], np.float32)
    keep = nms(boxes, np.array([0.9, 0.8, 0.7]), 0.4)
    assert keep == [0, 2]


def test_invalid_frame_raises(registry):
    import pytest
    with pytest.raises(ValueError):
        registry.detection.detector.detect(np.zeros((10, 10), np.uint8))
