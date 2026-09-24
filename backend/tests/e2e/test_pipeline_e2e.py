"""End-to-end tests on real models with LFW images.

1. Baseline recognition (Phase 11, no liveness): gallery of LFW people -> KNOWN / UNKNOWN / impostor.
2. Static-photo attack through the full API: repeated identical frames of an enrolled
   person must never produce KNOWN (passive PAD or the active challenge must stop it).
"""
import base64
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.core.config import Settings, get_settings, load_identity_threshold
from app.db.repositories import EmbeddingMeta
from app.services.frame_analyzer import FrameAnalyzer
from app.services.session_engine import SessionEngine
from tests.fakes import FakePeople, FakeSessions, FakeVectors

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evaluation" / "liveness"))
from pad_metrics import pad_metrics  # noqa: E402


def center_embedding(reg, img):
    c = np.array(img.shape[1::-1]) / 2
    face = min(reg.detection.detector.detect(img), key=lambda f: np.linalg.norm((f.bbox[:2] + f.bbox[2:]) / 2 - c))
    return reg.embedding.embed_one(reg.alignment.align(img, face.landmarks))


@pytest.fixture(scope="module")
def threshold(registry):
    thr = load_identity_threshold(get_settings(), registry.embedding.info.name)
    if thr is None:
        pytest.skip("identity threshold not calibrated yet")
    return thr


@pytest.fixture(scope="module")
def gallery(registry, lfw):
    people = FakePeople()
    vectors = FakeVectors(people)
    rec = registry.embedding.recognizer
    meta = EmbeddingMeta(rec.info.name, rec.info.version, rec.embedding_dimension, registry.alignment.version)
    ids = {}
    for name in ("Colin_Powell", "Tony_Blair", "Donald_Rumsfeld"):
        p = people.create(name, None, "ACTIVE")
        ids[name] = p["id"]
        for i in (1, 2, 3):
            vectors.insert(p["id"], center_embedding(registry, lfw(name, i)), meta)
    return people, vectors, meta, ids


def decide(vectors, meta, emb, thr):
    best = vectors.search(emb, meta)[0]
    return best["name"] if best["similarity"] >= thr else "UNKNOWN"


def test_baseline_known(registry, lfw, gallery, threshold):
    _, vectors, meta, _ = gallery
    for name in ("Colin_Powell", "Tony_Blair", "Donald_Rumsfeld"):
        assert decide(vectors, meta, center_embedding(registry, lfw(name, 5)), threshold) == name


def test_baseline_unknown_and_impostor(registry, lfw, gallery, threshold):
    _, vectors, meta, _ = gallery
    for name in ("George_W_Bush", "Gerhard_Schroeder", "Ariel_Sharon"):  # not enrolled
        assert decide(vectors, meta, center_embedding(registry, lfw(name, 1)), threshold) == "UNKNOWN"


def test_static_photo_attack_never_known(registry, lfw, gallery):
    people, vectors, meta, _ = gallery
    settings = Settings(identity_threshold_override=load_identity_threshold(get_settings(), meta.model_name) or 0.3,
                        action_timeout_s=1.0)
    sessions = FakeSessions()
    engine = SessionEngine(settings, FrameAnalyzer(registry, settings), sessions, people, vectors, meta)
    deps.set_container(deps.Container(settings, None, registry, people, sessions, vectors, engine))
    from app.main import app
    client = TestClient(app)
    try:
        photo = np.full((480, 640, 3), 100, np.uint8)
        photo[90:390, 170:470] = cv2.resize(lfw("Colin_Powell", 5)[40:210, 40:210], (300, 300))
        data = "data:image/jpeg;base64," + base64.b64encode(cv2.imencode(".jpg", photo)[1].tobytes()).decode()
        sid = client.post("/api/recognition/start").json()["data"]["session_id"]
        status = None
        for n in range(40):
            d = client.post("/api/recognition/frame",
                            json={"session_id": sid, "frame_number": n, "image_base64": data}).json()["data"]
            status = d["status"]
            if status in ("PASSED", "FAILED", "EXPIRED"):
                break
            time.sleep(0.1)
        assert status == "FAILED", d
        assert d["error_code"] in ("LIVENESS_FAILED", "CHALLENGE_FAILED")
        res = client.post("/api/recognition/complete", json={"session_id": sid}).json()["data"]
        assert res["result"] != "KNOWN" and "person" not in res
    finally:
        deps.set_container(None)


def test_pad_metrics_definitions():
    m = pad_metrics([{"category": "BONA_FIDE", "is_live": True}, {"category": "BONA_FIDE", "is_live": False},
                     {"category": "PRINT_ATTACK", "is_live": False}, {"category": "PHONE_VIDEO", "is_live": True},
                     {"category": "PHONE_VIDEO", "is_live": False}])
    assert (m["TP"], m["TN"], m["FP"], m["FN"]) == (2, 1, 1, 1)
    assert m["BPCER"] == 0.5 and m["APCER_per_species"]["PHONE_VIDEO"]["apcer"] == 0.5
    assert m["APCER_max"] == 0.5 and m["ACER"] == 0.5
