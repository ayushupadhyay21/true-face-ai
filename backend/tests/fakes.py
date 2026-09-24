"""In-memory fakes for session-engine and API tests (no models, no database)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np

from app.core.errors import ErrorCode
from app.db.repositories import EmbeddingMeta
from app.ml.base import DetectedFace, LivenessResult
from app.ml.quality.service import QualityResult
from app.ml.recognition.arcface import FaceEmbeddingService
from app.services.frame_analyzer import FrameAnalysis

META = EmbeddingMeta("fake_model", "v1", 8, "fake-prep")
DIM = 8


def unit(v) -> np.ndarray:
    v = np.asarray(v, np.float32)
    return v / np.linalg.norm(v)


PERSON_A = unit([1, 0, 0, 0, 0, 0, 0, 0])
PERSON_B = unit([0, 1, 0, 0, 0, 0, 0, 0])


class FakeLiveness:
    threshold = 0.5

    def aggregate(self, scores):
        s = float(np.mean(scores)) if scores else 0.0
        return LivenessResult(bool(scores) and s >= self.threshold, s, scores, "fake", "v1", "mean")


def frame(yaw=0.0, pitch=0.0, eyes=0.4, live=0.9, emb=PERSON_A, faces=1, quality_ok=True, x=100.0):
    """Build one FrameAnalysis the engine will receive."""
    if faces == 0:
        return FrameAnalysis(None, 0, ErrorCode.NO_FACE)
    if faces > 1:
        return FrameAnalysis(None, faces, ErrorCode.MULTIPLE_FACES)
    face = DetectedFace(np.array([x, 100, x + 150, 250], np.float32), np.zeros((5, 2), np.float32), 0.9)
    q = QualityResult(quality_ok, 150, 0.9, 200.0, 120.0, 40.0, yaw, pitch, 0.0,
                      None if quality_ok else "TOO_BLURRY")
    return FrameAnalysis(face, 1, None if quality_ok else ErrorCode.LOW_FACE_QUALITY, live, q, eyes,
                         emb if quality_ok else None)


class ScriptedAnalyzer:
    """Returns frames produced by `script(request)`; request carries the engine's needs."""

    def __init__(self):
        self.r = SimpleNamespace(liveness=FakeLiveness(), embedding=FaceEmbeddingService(None))
        self.queue: list[FrameAnalysis] = []
        self.calls: list[dict] = []

    def analyze(self, frame, *, require_frontal, need_eyes, need_embedding):
        self.calls.append({"require_frontal": require_frontal, "need_eyes": need_eyes,
                           "need_embedding": need_embedding})
        return self.queue.pop(0)


class FakeSessions:
    def __init__(self):
        self.rows, self.events, self.results = {}, [], {}

    def create(self, session_id, session_type, challenge, expires_at, person_id=None):
        self.rows[session_id] = {"session_id": session_id, "session_type": session_type, "status": "CREATED",
                                 "failure_code": None, "challenge": challenge, "expires_at": expires_at,
                                 "completed_at": None, "person_id": person_id}

    def update_status(self, session_id, status, failure_code=None, challenge=None):
        r = self.rows[session_id]
        r["status"] = status
        r["failure_code"] = failure_code or r["failure_code"]
        if challenge:
            r["challenge"] = challenge

    def mark_completed(self, session_id):
        r = self.rows[session_id]
        if r["completed_at"] is not None:
            return False
        r["completed_at"] = datetime.now(timezone.utc)
        return True

    def get(self, session_id):
        return self.rows.get(session_id)

    def add_liveness_event(self, session_id, frame_number, score, is_live, stage):
        self.events.append((session_id, frame_number, score, is_live, stage))

    def liveness_events(self, session_id):
        return [{"frame_number": e[1], "score": e[2], "prediction": "LIVE" if e[3] else "SPOOF", "stage": e[4]}
                for e in self.events if e[0] == session_id]

    def add_result(self, session_id, result, person_id=None, similarity=None, liveness=None, threshold=None,
                   model_name=None, model_version=None):
        self.results.setdefault(session_id, {"result": result, "person_id": person_id, "similarity": similarity})

    def get_result(self, session_id):
        return self.results.get(session_id)


class FakePeople:
    def __init__(self):
        self.rows = {}

    def create(self, name, external_id, status="PENDING"):
        pid = uuid.uuid4()
        now = datetime.now(timezone.utc)
        self.rows[pid] = {"id": pid, "name": name, "external_id": external_id, "status": status,
                          "created_at": now, "updated_at": now, "embedding_count": 0}
        return self.rows[pid]

    def get(self, pid):
        return self.rows.get(pid)

    def set_status(self, pid, status):
        self.rows[pid]["status"] = status

    def delete(self, pid):
        return self.rows.pop(pid, None) is not None


class FakeVectors:
    def __init__(self, people: FakePeople):
        self.people = people
        self.items: list[tuple[uuid.UUID, np.ndarray, str]] = []

    def insert(self, person_id, embedding, meta, pose=None, quality_score=None):
        self.items.append((person_id, np.asarray(embedding), pose))
        return uuid.uuid4()

    def search(self, embedding, meta, top_k=5, only_active=True):
        best = {}
        for pid, e, _ in self.items:
            p = self.people.get(pid)
            if p is None or (only_active and p["status"] != "ACTIVE"):
                continue
            best[pid] = max(best.get(pid, -1.0), float(e @ embedding))
        rows = [{"person_id": pid, "name": self.people.get(pid)["name"],
                 "external_id": self.people.get(pid)["external_id"], "similarity": s} for pid, s in best.items()]
        return sorted(rows, key=lambda r: r["similarity"], reverse=True)[:top_k]
