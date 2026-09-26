"""Live multi-face mode with real models and LFW faces, in-memory gallery (no PostgreSQL)."""
import base64
import uuid

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.db.repositories import EmbeddingMeta
from app.services.live_tracker import LiveTracker, iou
from tests.fakes import FakePeople, FakeSessions, FakeVectors


def center_embedding(reg, img):
    c = np.array(img.shape[1::-1]) / 2
    face = min(reg.detection.detector.detect(img), key=lambda f: np.linalg.norm((f.bbox[:2] + f.bbox[2:]) / 2 - c))
    return reg.embedding.embed_one(reg.alignment.align(img, face.landmarks))


@pytest.fixture()
def scene(registry, lfw):
    """640x480 frame with Colin Powell (left) and George W Bush (right); only Powell is enrolled."""
    people = FakePeople()
    vectors = FakeVectors(people)
    rec = registry.embedding.recognizer
    meta = EmbeddingMeta(rec.info.name, rec.info.version, rec.embedding_dimension, registry.alignment.version)
    p = people.create("Colin Powell", None, "ACTIVE")
    for i in (2, 3):
        vectors.insert(p["id"], center_embedding(registry, lfw("Colin_Powell", i)), meta)
    frame = np.full((480, 640, 3), 110, np.uint8)
    frame[140:340, 40:240] = cv2.resize(lfw("Colin_Powell", 1)[40:210, 40:210], (200, 200))
    frame[140:340, 400:600] = cv2.resize(lfw("George_W_Bush", 1)[40:210, 40:210], (200, 200))
    return people, vectors, meta, frame


def run(tracker, frame, n=7):
    live_id = uuid.UUID(tracker.start()["live_id"])
    out = None
    for k in range(n):
        out = tracker.process_frame(live_id, k, frame)
    return live_id, out


def test_multiple_faces_tracked_and_named(registry, scene):
    people, vectors, meta, frame = scene
    # liveness threshold 0 isolates the tracking/identity logic from the PAD decision
    tracker = LiveTracker(Settings(identity_threshold_override=0.3, liveness_threshold=0.0),
                          registry, people, vectors, meta)
    _, out = run(tracker, frame)
    assert out["face_count"] == 2
    faces = sorted(out["faces"], key=lambda f: f["bbox"][0])
    assert faces[0]["state"] == "KNOWN" and faces[0]["name"] == "Colin Powell"
    # Bush is not enrolled: auto-bucketed as a new UNASSIGNED person (snapshot, no name yet).
    assert faces[1]["state"] == "UNASSIGNED" and faces[1]["name"] is None and faces[1]["person_id"] is not None
    assert people.get(uuid.UUID(faces[1]["person_id"]))["status"] == "UNASSIGNED"
    assert {f["track_id"] for f in faces} == {1, 2}  # stable ids across 7 frames
    for f in faces:
        x1, y1, x2, y2 = f["bbox"]
        assert 0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1


def test_unassigned_face_reuses_same_person_next_session(registry, scene):
    people, vectors, meta, frame = scene
    settings = Settings(identity_threshold_override=0.3, liveness_threshold=0.0)
    first = LiveTracker(settings, registry, people, vectors, meta)
    _, out = run(first, frame)
    bush = sorted(out["faces"], key=lambda f: f["bbox"][0])[1]
    assert bush["state"] == "UNASSIGNED"

    second = LiveTracker(settings, registry, people, vectors, meta)
    _, out2 = run(second, frame)
    bush2 = sorted(out2["faces"], key=lambda f: f["bbox"][0])[1]
    assert bush2["person_id"] == bush["person_id"]  # same unnamed face, same row, not a duplicate
    assert len(people.list("UNASSIGNED")) == 1


def test_no_name_before_liveness_frames(registry, scene):
    people, vectors, meta, frame = scene
    tracker = LiveTracker(Settings(identity_threshold_override=0.3, liveness_threshold=0.0),
                          registry, people, vectors, meta)
    _, out = run(tracker, frame, n=2)
    assert all(f["state"] == "CHECKING" and f["name"] is None for f in out["faces"])


def test_spoof_tracks_never_named(registry, scene):
    people, vectors, meta, frame = scene
    tracker = LiveTracker(Settings(identity_threshold_override=0.3, liveness_threshold=1.01),
                          registry, people, vectors, meta)
    _, out = run(tracker, frame)
    assert all(f["state"] == "SPOOF" and f["name"] is None and f["similarity"] is None for f in out["faces"])


def test_replayed_frame_and_unknown_session(registry, scene):
    people, vectors, meta, frame = scene
    tracker = LiveTracker(Settings(identity_threshold_override=0.3), registry, people, vectors, meta)
    live_id, _ = run(tracker, frame, n=1)
    with pytest.raises(AppError) as e:
        tracker.process_frame(live_id, 0, frame)
    assert e.value.code == ErrorCode.INVALID_FRAME
    assert tracker.stop(live_id)["stopped"] is True
    with pytest.raises(AppError) as e:
        tracker.process_frame(live_id, 5, frame)
    assert e.value.code == ErrorCode.SESSION_NOT_FOUND


def test_iou():
    a = np.array([0, 0, 10, 10], float)
    assert iou(a, a) == 1.0 and iou(a, np.array([20, 20, 30, 30], float)) == 0.0


def test_live_api(registry, scene):
    people, vectors, meta, frame = scene
    settings = Settings(identity_threshold_override=0.3, liveness_threshold=0.0)
    tracker = LiveTracker(settings, registry, people, vectors, meta)
    deps.set_container(deps.Container(settings, None, registry, people, FakeSessions(), vectors, None, tracker))
    from app.main import app
    client = TestClient(app)
    try:
        live_id = client.post("/api/live/start").json()["data"]["live_id"]
        img = "data:image/jpeg;base64," + base64.b64encode(cv2.imencode(".jpg", frame)[1].tobytes()).decode()
        data = None
        for k in range(6):
            r = client.post("/api/live/frame", json={"live_id": live_id, "frame_number": k, "image_base64": img})
            assert r.status_code == 200, r.text
            data = r.json()["data"]
        assert data["frame_width"] == 640 and data["face_count"] == 2
        assert "Colin Powell" in [f["name"] for f in data["faces"]]
        assert client.post("/api/live/stop", json={"live_id": live_id}).json()["data"]["stopped"] is True
    finally:
        deps.set_container(None)
