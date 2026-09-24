from __future__ import annotations

import os
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
LFW = ROOT / "datasets" / "lfw" / "lfw"


@pytest.fixture(scope="session")
def registry():
    from app.ml.registry import get_registry
    try:
        return get_registry()
    except Exception as e:  # models not downloaded
        pytest.skip(f"models unavailable: {e}")


def _lfw(name: str, idx: int) -> np.ndarray:
    path = LFW / name / f"{name}_{idx:04d}.jpg"
    if not path.exists():
        pytest.skip("LFW test images not available (datasets/lfw)")
    return cv2.imread(str(path))


@pytest.fixture(scope="session")
def lfw():
    return _lfw


@pytest.fixture(scope="session")
def face_img(lfw):
    """A single-subject LFW image (centre face cropped out so background faces are excluded)."""
    img = lfw("Colin_Powell", 1)
    return img[40:210, 40:210].copy()


def db_conninfo() -> str | None:
    from app.core.config import get_settings
    s = get_settings()
    if not s.postgres_password and not os.environ.get("PGPASSWORD"):
        return None
    return s.database_url


@pytest.fixture(scope="session")
def database():
    from app.db.database import Database, apply_migrations
    info = db_conninfo()
    if info is None:
        pytest.skip("PostgreSQL credentials not configured (.env)")
    try:
        apply_migrations(info)
        db = Database(info)
        if db.ping()["pgvector"] is None:
            pytest.skip("pgvector extension not installed")
    except Exception as e:
        pytest.skip(f"PostgreSQL unavailable: {e}")
    return db


@pytest.fixture()
def clean_db(database):
    with database.connect() as c:
        c.execute("TRUNCATE people, face_embeddings, recognition_sessions, recognition_results, liveness_events "
                  "CASCADE")
    return database
