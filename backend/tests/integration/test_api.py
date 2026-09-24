"""API tests: real FastAPI app + real models, in-memory repositories (no PostgreSQL needed)."""
import base64
import uuid

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.core.config import Settings
from app.db.repositories import EmbeddingMeta
from app.services.frame_analyzer import FrameAnalyzer
from app.services.session_engine import SessionEngine
from tests.fakes import FakePeople, FakeSessions, FakeVectors


class FakeDB:
    def ping(self):
        return {"postgres": "fake", "pgvector": "0.0"}


@pytest.fixture()
def client(registry):
    settings = Settings(identity_threshold_override=0.4)
    people, sessions = FakePeople(), FakeSessions()
    vectors = FakeVectors(people)
    rec = registry.embedding.recognizer
    meta = EmbeddingMeta(rec.info.name, rec.info.version, rec.embedding_dimension, registry.alignment.version)
    engine = SessionEngine(settings, FrameAnalyzer(registry, settings), sessions, people, vectors, meta)
    deps.set_container(deps.Container(settings, FakeDB(), registry, people, sessions, vectors, engine))
    from app.main import app
    yield TestClient(app)
    deps.set_container(None)


def b64(img) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(cv2.imencode(".jpg", img)[1].tobytes()).decode()


def test_health(client):
    r = client.get("/health").json()
    assert r["ok"] and r["data"]["database_ok"]
    m = client.get("/health/models").json()["data"]
    assert m["models"]["recognizer"]["embedding_dimension"] == 512
    assert m["calibrated"] is True


def test_person_crud_and_validation(client):
    r = client.post("/api/person", json={"name": "  Ada ", "external_id": "E1"})
    assert r.status_code == 201 and r.json()["data"]["name"] == "Ada"
    pid = r.json()["data"]["id"]
    assert client.get(f"/api/person/{pid}").json()["data"]["status"] == "PENDING"
    bad = client.post("/api/person", json={"name": ""})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "INVALID_REQUEST"
    extra = client.post("/api/person", json={"name": "x", "role": "admin"})
    assert extra.status_code == 422
    assert client.get("/api/person/not-a-uuid").status_code == 422
    missing = client.get(f"/api/person/{uuid.uuid4()}")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "PERSON_NOT_FOUND"
    assert client.delete(f"/api/person/{pid}").json()["ok"]
    assert client.delete(f"/api/person/{pid}").status_code == 404


def test_recognition_frame_flow_and_errors(client, face_img):
    s = client.post("/api/recognition/start").json()["data"]
    sid = s["session_id"]
    img = cv2.resize(face_img, (480, 480))
    r = client.post("/api/recognition/frame", json={"session_id": sid, "frame_number": 0, "image_base64": b64(img)})
    body = r.json()
    assert r.status_code == 200, body
    f = body["data"]["frame"]
    assert f["face_count"] == 1 and f["liveness_frame_score"] is not None
    assert "person" not in body["data"]  # no identity during the session

    # replayed frame number
    r = client.post("/api/recognition/frame", json={"session_id": sid, "frame_number": 0, "image_base64": b64(img)})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_FRAME"
    # garbage image
    r = client.post("/api/recognition/frame",
                    json={"session_id": sid, "frame_number": 5, "image_base64": base64.b64encode(b"x" * 200).decode()})
    assert r.json()["error"]["code"] == "INVALID_FRAME"
    # complete before liveness done
    r = client.post("/api/recognition/complete", json={"session_id": sid})
    assert r.status_code == 409 and r.json()["error"]["code"] == "SESSION_STATE"
    # wrong endpoint type
    r = client.post("/api/enrollment/frame", json={"session_id": sid, "frame_number": 9, "image_base64": b64(img)})
    assert r.status_code == 409
    # status endpoints
    assert client.get(f"/api/recognition/{sid}").json()["data"]["status"] == "IN_PROGRESS"
    ev = client.get(f"/api/liveness/{sid}").json()["data"]["events"]
    assert len(ev) == 1


def test_multiple_faces_via_api(client, lfw):
    pair = np.hstack([lfw("Colin_Powell", 1)[40:210, 40:210], lfw("George_W_Bush", 1)[40:210, 40:210]])
    sid = client.post("/api/recognition/start").json()["data"]["session_id"]
    r = client.post("/api/recognition/frame", json={"session_id": sid, "frame_number": 0, "image_base64": b64(pair)})
    d = r.json()["data"]
    assert d["status"] == "FAILED" and d["error_code"] == "MULTIPLE_FACES"
    c = client.post("/api/recognition/complete", json={"session_id": sid}).json()["data"]
    assert c["result"] == "MULTIPLE_FACES" and "person" not in c
    again = client.post("/api/recognition/complete", json={"session_id": sid})
    assert again.status_code == 409


def test_unknown_session_and_enrollment_unknown_person(client):
    r = client.post("/api/recognition/frame",
                    json={"session_id": str(uuid.uuid4()), "frame_number": 0, "image_base64": "A" * 200})
    assert r.status_code == 404 and r.json()["error"]["code"] == "SESSION_NOT_FOUND"
    r = client.post("/api/enrollment/start", json={"person_id": str(uuid.uuid4())})
    assert r.status_code == 404


def test_internal_errors_hide_details(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("secret internal detail")
    monkeypatch.setattr(deps.get_container().engine, "start", boom)
    r = TestClient(client.app, raise_server_exceptions=False).post("/api/recognition/start")
    assert r.status_code == 500
    assert "secret" not in r.text and r.json()["error"]["code"] == "INTERNAL_ERROR"
