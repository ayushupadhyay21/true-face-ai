"""PostgreSQL + pgvector tests. Skipped unless .env has working credentials and pgvector."""
import uuid

import numpy as np
import psycopg
import pytest

from app.core.errors import AppError
from app.db.repositories import EmbeddingMeta, PeopleRepository, SessionRepository, VectorSearchService

pytestmark = pytest.mark.db
META = EmbeddingMeta("test_model", "v1", 512, "prep-v1")


def unit(v):
    v = np.asarray(v, np.float32)
    return v / np.linalg.norm(v)


@pytest.fixture()
def repos(clean_db):
    return PeopleRepository(clean_db), VectorSearchService(clean_db), SessionRepository(clean_db)


def test_vector_search_synthetic(repos):
    people, vectors, _ = repos
    rng = np.random.default_rng(0)
    a = people.create("A", "a")
    b = people.create("B", "b")
    for p in (a, b):
        people.set_status(p["id"], "ACTIVE")
    va, vb = unit(rng.normal(size=512)), unit(rng.normal(size=512))
    vectors.insert(a["id"], va, META, "CENTER")
    vectors.insert(a["id"], unit(va + 0.3 * unit(rng.normal(size=512))), META, "LEFT")  # multiple per person
    vectors.insert(b["id"], vb, META, "CENTER")

    exact = vectors.search(va, META)
    assert exact[0]["person_id"] == a["id"] and exact[0]["similarity"] == pytest.approx(1.0, abs=1e-5)
    assert exact[0]["matched_embeddings"] == 2 and len(exact) == 2  # grouped per person

    near = vectors.search(unit(va + 0.2 * unit(rng.normal(size=512))), META)
    assert near[0]["person_id"] == a["id"] and near[0]["similarity"] > 0.9

    unrelated = vectors.search(unit(rng.normal(size=512)), META)
    assert max(r["similarity"] for r in unrelated) < 0.3


def test_empty_database_and_model_isolation(repos):
    people, vectors, _ = repos
    assert vectors.search(unit(np.ones(512)), META) == []
    p = people.create("C", None, "ACTIVE")
    vectors.insert(p["id"], unit(np.ones(512)), META)
    other = EmbeddingMeta("test_model", "v2", 512, "prep-v1")
    assert vectors.search(unit(np.ones(512)), other) == []  # never mix model versions


def test_dimension_mismatch_rejected(repos):
    people, vectors, _ = repos
    p = people.create("D", None)
    with pytest.raises(AppError):
        vectors.insert(p["id"], unit(np.ones(128)), META)


def test_cascade_delete(repos, clean_db):
    people, vectors, _ = repos
    p = people.create("E", None, "ACTIVE")
    vectors.insert(p["id"], unit(np.ones(512)), META)
    assert people.delete(p["id"])
    assert vectors.count() == 0


def test_inactive_people_excluded(repos):
    people, vectors, _ = repos
    p = people.create("F", None, "PENDING")
    vectors.insert(p["id"], unit(np.ones(512)), META)
    assert vectors.search(unit(np.ones(512)), META) == []
    assert len(vectors.search(unit(np.ones(512)), META, only_active=False)) == 1


def test_duplicate_external_id(repos):
    people, *_ = repos
    people.create("G", "same")
    with pytest.raises(AppError) as e:
        people.create("H", "same")
    assert e.value.status == 409


def test_sessions_completion_is_atomic(repos):
    from datetime import datetime, timedelta, timezone
    _, _, sessions = repos
    sid = uuid.uuid4()
    sessions.create(sid, "RECOGNITION", {"x": 1}, datetime.now(timezone.utc) + timedelta(minutes=1))
    sessions.add_liveness_event(sid, 0, 0.9, True, "PASSIVE")
    sessions.add_liveness_event(sid, 0, 0.1, False, "PASSIVE")  # duplicate frame ignored
    assert len(sessions.liveness_events(sid)) == 1
    assert sessions.mark_completed(sid) is True
    assert sessions.mark_completed(sid) is False
    sessions.add_result(sid, "UNKNOWN", similarity=0.1)
    assert sessions.get_result(sid)["result"] == "UNKNOWN"


def test_constraints(clean_db):
    with pytest.raises(AppError):
        with clean_db.connect() as c:
            c.execute("INSERT INTO people(name, status) VALUES ('x', 'BOGUS')")
    with pytest.raises(AppError):
        with clean_db.connect() as c:
            c.execute("INSERT INTO liveness_events(session_id, frame_number, score, prediction) "
                      "VALUES (%s, 0, 1.5, 'LIVE')", (uuid.uuid4(),))
    assert psycopg  # imported for clarity of the error source
