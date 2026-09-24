import numpy as np
import pytest

from app.ml.liveness.silentface import crop_patch, parse_model_name


def _embed(registry, img):
    face = registry.detection.detect_single(img).face
    return registry.embedding.embed_one(registry.alignment.align(img, face.landmarks))


def test_embedding_shape_norm_finite_deterministic(registry, face_img):
    e1, e2 = _embed(registry, face_img), _embed(registry, face_img)
    assert e1.shape == (registry.embedding.recognizer.embedding_dimension,)
    assert registry.embedding.recognizer.embedding_dimension == 512  # read from graph, checked here
    assert np.isfinite(e1).all()
    assert abs(np.linalg.norm(e1) - 1) < 1e-5
    assert np.array_equal(e1, e2)


def _embed_center(registry, img):
    """LFW images can hold background faces; take the centre one (test data only)."""
    c = np.array(img.shape[1::-1]) / 2
    face = min(registry.detection.detector.detect(img), key=lambda f: np.linalg.norm((f.bbox[:2] + f.bbox[2:]) / 2 - c))
    return registry.embedding.embed_one(registry.alignment.align(img, face.landmarks))


def test_same_person_more_similar_than_different(registry, lfw):
    a1 = _embed_center(registry, lfw("Colin_Powell", 1))
    a2 = _embed_center(registry, lfw("Colin_Powell", 2))
    b = _embed_center(registry, lfw("George_W_Bush", 1))
    assert float(a1 @ a2) > float(a1 @ b) + 0.2


def test_embedding_wrong_size_raises(registry):
    with pytest.raises(ValueError):
        registry.embedding.recognizer.embed([np.zeros((100, 100, 3), np.uint8)])


def test_embedding_empty_batch(registry):
    assert registry.embedding.recognizer.embed([]).shape == (0, 512)


def test_parse_model_name_matches_upstream():
    assert parse_model_name("2.7_80x80_MiniFASNetV2") == (2.7, 80, 80)
    assert parse_model_name("4_0_0_80x80_MiniFASNetV1SE") == (4.0, 80, 80)
    assert parse_model_name("org_1_80x60_MiniFASNetV1SE") == (None, 80, 60)


def test_crop_patch_shifts_inside_image():
    img = np.arange(200 * 300 * 3, dtype=np.uint32).reshape(200, 300, 3).astype(np.uint8)
    patch = crop_patch(img, (0, 0, 50, 50), 2.7, 80, 80)  # box at the corner must shift, not pad
    assert patch.shape == (80, 80, 3)
    patch = crop_patch(img, (100, 50, 180, 180), 4.0, 80, 80)  # scale clamps to image size
    assert patch.shape == (80, 80, 3)


def test_liveness_scores_are_probabilities(registry, face_img):
    face = registry.detection.detect_single(face_img).face
    s = registry.liveness.frame_score(face_img, face)
    assert 0.0 <= s <= 1.0
    r = registry.liveness.predict([(face_img, face)] * 3)
    assert r.aggregation == "mean_over_3_frames"
    assert r.frame_scores == [round(s, 4)] * 3
    assert r.model and r.model_version


def test_liveness_aggregate_rule(registry):
    agg = registry.liveness.aggregate
    thr = registry.liveness.threshold
    assert agg([thr + 0.1] * 5).is_live
    assert not agg([thr - 0.1] * 5).is_live
    assert not agg([]).is_live
    assert agg([0.9, 0.9, 0.1]).score == pytest.approx(np.mean([0.9, 0.9, 0.1]))
