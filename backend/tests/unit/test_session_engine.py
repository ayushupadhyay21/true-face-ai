import uuid
from datetime import timedelta

import numpy as np
import pytest

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.services.session_engine import ENROLLMENT, RECOGNITION, SessionEngine
from tests.fakes import (META, PERSON_A, PERSON_B, FakePeople, FakeSessions, FakeVectors, ScriptedAnalyzer,
                         frame, unit)

IMG = np.zeros((10, 10, 3), np.uint8)
S = Settings(identity_threshold_override=0.5, liveness_min_frames=3, active_liveness_enabled=True)


def action_frames(action, emb=PERSON_A, live=0.9):
    y, p = S.yaw_delta + 0.05, S.pitch_delta + 0.05
    return {
        "LOOK_LEFT": [frame(yaw=y, emb=emb, live=live)] * 2,
        "LOOK_RIGHT": [frame(yaw=-y, emb=emb, live=live)] * 2,
        "LOOK_UP": [frame(pitch=-p, emb=emb, live=live)] * 2,
        "LOOK_DOWN": [frame(pitch=p, emb=emb, live=live)] * 2,
        "BLINK": [frame(eyes=0.1, emb=emb, live=live), frame(eyes=0.4, emb=emb, live=live)],
        "CENTER": [frame(emb=emb, live=live)] * 2,
    }[action]


@pytest.fixture()
def env():
    analyzer, sessions, people = ScriptedAnalyzer(), FakeSessions(), FakePeople()
    vectors = FakeVectors(people)
    engine = SessionEngine(S, analyzer, sessions, people, vectors, META)
    return engine, analyzer, sessions, people, vectors


class Driver:
    def __init__(self, engine, analyzer, sid):
        self.engine, self.analyzer, self.sid, self.n = engine, analyzer, uuid.UUID(sid), 0

    def send(self, fa):
        self.analyzer.queue.append(fa)
        out = self.engine.process_frame(self.sid, self.n, IMG)
        self.n += 1
        return out

    def passive(self, emb=PERSON_A, live=0.9):
        out = None
        for _ in range(S.liveness_min_frames):
            out = self.send(frame(emb=emb, live=live))
        return out

    def run_actions(self, emb=PERSON_A, center_emb=None, live=0.9):
        out = None
        while True:
            st = self.engine._get(self.sid)
            if st.status != "IN_PROGRESS" or st.current_action is None:
                return out
            e = center_emb if (center_emb is not None and st.current_action.value == "CENTER") else emb
            for fa in action_frames(st.current_action.value, e, live):
                out = self.send(fa)


def enroll(env, emb=PERSON_A, name="Alice"):
    engine, analyzer, _, people, _ = env
    person = people.create(name, None)
    start = engine.start(ENROLLMENT, person["id"])
    d = Driver(engine, analyzer, start["session_id"])
    d.passive(emb)
    out = d.run_actions(emb)
    assert out["status"] == "PASSED", out
    return person, engine.complete(d.sid, ENROLLMENT)


def test_enrollment_then_recognition_known(env):
    engine, analyzer, sessions, people, vectors = env
    person, res = enroll(env)
    assert res["result"] == "ENROLLED"
    assert {"CENTER", "LEFT", "RIGHT"} <= set(res["poses"])
    assert people.get(person["id"])["status"] == "ACTIVE"

    start = engine.start(RECOGNITION)
    assert start["status"] == "CREATED" and start["current_action"] is None
    d = Driver(engine, analyzer, start["session_id"])
    d.passive()
    assert d.run_actions()["status"] == "PASSED"
    res = engine.complete(d.sid, RECOGNITION)
    assert res["result"] == "KNOWN" and res["person"]["name"] == "Alice"
    assert len(sessions.events) > 0


def test_passive_only_mode_finishes_without_instruction():
    settings = Settings(identity_threshold_override=0.5, liveness_min_frames=3, active_liveness_enabled=False)
    analyzer, sessions, people = ScriptedAnalyzer(), FakeSessions(), FakePeople()
    vectors = FakeVectors(people)
    engine = SessionEngine(settings, analyzer, sessions, people, vectors, META)
    start = engine.start(RECOGNITION)
    driver = Driver(engine, analyzer, start["session_id"])

    out = driver.passive()

    assert out["status"] == "PASSED"
    assert out["phase"] == "DONE"
    assert out["instruction"] is None


def test_unknown_person_not_forced(env):
    engine, analyzer, *_ = env
    enroll(env)
    d = Driver(engine, analyzer, engine.start(RECOGNITION)["session_id"])
    d.passive(PERSON_B)
    d.run_actions(PERSON_B)
    res = engine.complete(d.sid, RECOGNITION)
    assert res["result"] == "UNKNOWN" and "person" not in res


def test_spoof_fails_passive_and_hides_identity(env):
    engine, analyzer, *_ = env
    enroll(env)
    d = Driver(engine, analyzer, engine.start(RECOGNITION)["session_id"])
    out = d.passive(live=0.1)
    assert out["status"] == "FAILED" and out["error_code"] == "LIVENESS_FAILED"
    res = engine.complete(d.sid, RECOGNITION)
    assert res["result"] == "LIVENESS_FAILED" and "person" not in res and "similarity" not in res


def test_spoof_during_active_phase_fails_whole_session_check(env):
    engine, analyzer, *_ = env
    enroll(env)
    d = Driver(engine, analyzer, engine.start(RECOGNITION)["session_id"])
    d.passive(live=0.55)
    out = d.run_actions(live=0.05)
    assert out["status"] == "FAILED" and out["error_code"] == "LIVENESS_FAILED"


def test_multiple_faces_fails_session(env):
    engine, analyzer, *_ = env
    enroll(env)
    d = Driver(engine, analyzer, engine.start(RECOGNITION)["session_id"])
    d.send(frame())
    out = d.send(frame(faces=2))
    assert out["status"] == "FAILED" and out["error_code"] == "MULTIPLE_FACES"
    with pytest.raises(AppError) as e:
        d.send(frame())
    assert e.value.code == ErrorCode.SESSION_STATE


def test_no_face_waits(env):
    engine, analyzer, *_ = env
    enroll(env)
    d = Driver(engine, analyzer, engine.start(RECOGNITION)["session_id"])
    out = d.send(frame(faces=0))
    assert out["status"] == "IN_PROGRESS" and out["frame"]["frame_error"] == "NO_FACE"


def test_low_quality_frames_not_counted(env):
    engine, analyzer, *_ = env
    enroll(env)
    d = Driver(engine, analyzer, engine.start(RECOGNITION)["session_id"])
    for _ in range(5):
        out = d.send(frame(quality_ok=False))
    assert out["phase"] == "PASSIVE" and out["passive_frames"] == 0


def test_old_or_repeated_frame_rejected(env):
    engine, analyzer, *_ = env
    enroll(env)
    d = Driver(engine, analyzer, engine.start(RECOGNITION)["session_id"])
    d.send(frame())
    d.n = 0
    with pytest.raises(AppError) as e:
        d.send(frame())
    assert e.value.code == ErrorCode.INVALID_FRAME


def test_face_swap_between_passive_and_center_detected(env):
    engine, analyzer, *_ = env
    enroll(env)
    d = Driver(engine, analyzer, engine.start(RECOGNITION)["session_id"])
    d.passive(PERSON_A)
    out = d.run_actions(PERSON_A, center_emb=PERSON_B)
    assert out["status"] == "FAILED" and out["error_code"] == "CHALLENGE_FAILED"


def test_face_jump_detected(env):
    engine, analyzer, *_ = env
    enroll(env)
    d = Driver(engine, analyzer, engine.start(RECOGNITION)["session_id"])
    d.send(frame(x=100))
    out = d.send(frame(x=400))
    assert out["status"] == "FAILED" and out["error_code"] == "CHALLENGE_FAILED"


def test_expired_session(env):
    engine, analyzer, sessions, *_ = env
    enroll(env)
    sid = uuid.UUID(engine.start(RECOGNITION)["session_id"])
    engine._get(sid).expires_at -= timedelta(seconds=S.challenge_timeout_s + 1)
    with pytest.raises(AppError) as e:
        engine.process_frame(sid, 0, IMG)
    assert e.value.code == ErrorCode.SESSION_EXPIRED
    assert sessions.rows[sid]["status"] == "EXPIRED"


def test_action_timeout(env):
    engine, analyzer, *_ = env
    enroll(env)
    d = Driver(engine, analyzer, engine.start(RECOGNITION)["session_id"])
    d.passive()
    st = engine._get(d.sid)
    st.action_started_at -= timedelta(seconds=S.action_timeout_s + 1)
    out = d.send(frame())
    assert out["status"] == "FAILED" and out["error_code"] == "CHALLENGE_FAILED"


def test_unknown_session(env):
    engine, *_ = env
    with pytest.raises(AppError) as e:
        engine.process_frame(uuid.uuid4(), 0, IMG)
    assert e.value.code == ErrorCode.SESSION_NOT_FOUND


def test_complete_before_liveness_and_duplicate_completion(env):
    engine, analyzer, *_ = env
    enroll(env)
    d = Driver(engine, analyzer, engine.start(RECOGNITION)["session_id"])
    with pytest.raises(AppError) as e:
        engine.complete(d.sid, RECOGNITION)
    assert e.value.code == ErrorCode.SESSION_STATE
    d.passive()
    d.run_actions()
    assert engine.complete(d.sid, RECOGNITION)["result"] == "KNOWN"
    with pytest.raises(AppError) as e:
        engine.complete(d.sid, RECOGNITION)
    assert e.value.code == ErrorCode.SESSION_STATE


def test_wrong_session_type(env):
    engine, analyzer, *_ = env
    person, _ = enroll(env)
    sid = uuid.UUID(engine.start(RECOGNITION)["session_id"])
    with pytest.raises(AppError):
        engine.complete(sid, ENROLLMENT)


def test_duplicate_identity_enrollment_refused(env):
    enroll(env, PERSON_A, "Alice")
    with pytest.raises(AppError) as e:
        enroll(env, unit(PERSON_A + 0.05), "Mallory")
    assert e.value.status == 409
    assert "Alice" in e.value.message
    assert e.value.details["matched_person"]["name"] == "Alice" and e.value.details["similarity"] > 0.5


def test_not_calibrated_blocks_start(env):
    _, analyzer, sessions, people, vectors = env
    engine = SessionEngine(Settings(calibration_file="nonexistent.json"), analyzer, sessions, people, vectors, META)
    with pytest.raises(AppError) as e:
        engine.start(RECOGNITION)
    assert e.value.code == ErrorCode.NOT_CALIBRATED


def test_identity_never_searched_before_pass(env):
    engine, analyzer, _, _, vectors = env
    enroll(env)
    calls = []
    original = vectors.search
    vectors.search = lambda *a, **k: calls.append(1) or original(*a, **k)
    d = Driver(engine, analyzer, engine.start(RECOGNITION)["session_id"])
    d.passive()
    d.run_actions()
    assert calls == []
    engine.complete(d.sid, RECOGNITION)
    assert calls == [1]


def test_challenge_not_exposed_upfront(env):
    engine, *_ = env
    enroll(env)
    start = engine.start(RECOGNITION)
    assert "expected_actions" not in start and start["current_action"] is None
