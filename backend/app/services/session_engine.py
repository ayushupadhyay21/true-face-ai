"""Enrollment and recognition sessions: passive PAD -> active challenge -> identity.

Life cycle (status): CREATED -> IN_PROGRESS -> PASSED | FAILED | EXPIRED.
Phases inside IN_PROGRESS: PASSIVE (collect N good frontal frames, aggregate PAD score,
measure baseline pose/eyes) -> ACTIVE (random action sequence ending with CENTER).

Rules enforced here (see SECURITY.md):
  * 0 faces -> wait; 2+ faces -> session FAILED (MULTIPLE_FACES). Never pick one face.
  * Frame numbers must strictly increase (no replayed or re-ordered frames).
  * Frames must keep arriving (gap <= max_frame_gap_s) and the face may not jump position.
  * The final CENTER embedding must match the passive-phase embedding (same person throughout).
  * The identity search runs only in `complete()` and only when status is PASSED.
  * `complete()` succeeds once per session (atomic completed_at update).
  * Failure responses never carry identity information.

Session runtime state is kept in memory (single local process). A server restart drops
in-progress sessions; their DB rows then read as not found for frame submission.
"""
from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np

from app.core.config import Settings, load_identity_threshold
from app.core.errors import AppError, ErrorCode
from app.db.repositories import EmbeddingMeta
from app.services.challenge import INSTRUCTIONS, Action, ActionEvaluator, Baseline, Observation, generate_actions

log = logging.getLogger(__name__)

ENROLLMENT = "ENROLLMENT"
RECOGNITION = "RECOGNITION"
SIDE_POSES = {Action.LOOK_LEFT: "LEFT", Action.LOOK_RIGHT: "RIGHT"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Sample:
    embedding: np.ndarray
    pose: str
    quality: float  # blur score, used to rank centre samples


@dataclass
class SessionState:
    session_id: uuid.UUID
    session_type: str
    person_id: uuid.UUID | None
    actions: list[Action]
    challenge_id: uuid.UUID
    created_at: datetime
    expires_at: datetime
    status: str = "CREATED"
    phase: str = "PASSIVE"
    failure_code: ErrorCode | None = None
    action_index: int = 0
    action_started_at: datetime | None = None
    evaluator: ActionEvaluator | None = None
    last_frame_number: int = -1
    last_frame_at: datetime | None = None
    last_center: np.ndarray | None = None
    passive_scores: list[float] = field(default_factory=list)
    all_scores: list[float] = field(default_factory=list)
    baseline_obs: list[tuple[float, float, float]] = field(default_factory=list)
    baseline: Baseline | None = None
    center_samples: list[Sample] = field(default_factory=list)
    side_samples: list[Sample] = field(default_factory=list)
    final_samples: list[Sample] = field(default_factory=list)
    liveness_score: float | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def current_action(self) -> Action | None:
        if self.phase != "ACTIVE" or self.action_index >= len(self.actions):
            return None
        return self.actions[self.action_index]

    def challenge_json(self) -> dict:
        return {"challenge_id": str(self.challenge_id), "expected_actions": [a.value for a in self.actions],
                "current_action": self.current_action.value if self.current_action else None,
                "completed_actions": self.action_index, "created_at": self.created_at.isoformat(),
                "expires_at": self.expires_at.isoformat()}


class SessionEngine:
    def __init__(self, settings: Settings, analyzer, sessions_repo, people_repo, vectors, model_meta: EmbeddingMeta):
        self.s = settings
        self.analyzer = analyzer
        self.sessions_repo = sessions_repo
        self.people = people_repo
        self.vectors = vectors
        self.meta = model_meta
        self._sessions: dict[uuid.UUID, SessionState] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ helpers
    def identity_threshold(self) -> float:
        thr = load_identity_threshold(self.s, self.meta.model_name)
        if thr is None:
            raise AppError(ErrorCode.NOT_CALIBRATED,
                           "Recognition threshold not calibrated for the current model "
                           "(run evaluation/recognition/calibrate_threshold.py)")
        return thr

    def consistency_threshold(self) -> float:
        return self.s.session_consistency_threshold or self.identity_threshold()

    def _get(self, session_id: uuid.UUID) -> SessionState:
        st = self._sessions.get(session_id)
        if st is None:
            raise AppError(ErrorCode.SESSION_NOT_FOUND, "Session not found or no longer active")
        return st

    def _fail(self, st: SessionState, code: ErrorCode) -> None:
        st.status = "FAILED"
        st.failure_code = code
        st.phase = "DONE"
        self.sessions_repo.update_status(st.session_id, "FAILED", code.value, st.challenge_json())
        log.info("session %s failed: %s", st.session_id, code.value)

    def _check_expiry(self, st: SessionState) -> None:
        if st.status in ("CREATED", "IN_PROGRESS") and utcnow() > st.expires_at:
            st.status = "EXPIRED"
            st.phase = "DONE"
            st.failure_code = ErrorCode.SESSION_EXPIRED
            self.sessions_repo.update_status(st.session_id, "EXPIRED", ErrorCode.SESSION_EXPIRED.value)
        if st.status == "EXPIRED":
            raise AppError(ErrorCode.SESSION_EXPIRED, "Session expired")

    # ------------------------------------------------------------------ start
    def start(self, session_type: str, person_id: uuid.UUID | None = None) -> dict:
        self.identity_threshold()  # refuse to start sessions that could never be decided
        required: tuple[Action, ...] = ()
        if session_type == ENROLLMENT:
            person = self.people.get(person_id)
            if person is None:
                raise AppError(ErrorCode.PERSON_NOT_FOUND, "Person not found")
            if person["status"] == "DISABLED":
                raise AppError(ErrorCode.INVALID_REQUEST, "Person is disabled")
            required = (Action.LOOK_LEFT, Action.LOOK_RIGHT)
        now = utcnow()
        actions = generate_actions(self.s.challenge_length, required=required) if self.s.active_liveness_enabled else []
        st = SessionState(session_id=uuid.uuid4(), session_type=session_type, person_id=person_id,
                  actions=actions,
                          challenge_id=uuid.uuid4(), created_at=now,
                          expires_at=now + timedelta(seconds=self.s.challenge_timeout_s))
        self.sessions_repo.create(st.session_id, session_type, st.challenge_json(), st.expires_at, person_id)
        with self._lock:
            self._purge_locked()
            self._sessions[st.session_id] = st
        return self.describe(st)

    def _purge_locked(self) -> None:
        cutoff = utcnow() - timedelta(minutes=10)
        for sid in [k for k, v in self._sessions.items() if v.expires_at < cutoff]:
            del self._sessions[sid]

    # ------------------------------------------------------------------ frames
    def process_frame(self, session_id: uuid.UUID, frame_number: int, frame: np.ndarray) -> dict:
        st = self._get(session_id)
        with st.lock:
            self._check_expiry(st)
            if st.status not in ("CREATED", "IN_PROGRESS"):
                raise AppError(ErrorCode.SESSION_STATE, f"Session is {st.status}; no more frames accepted")
            if frame_number <= st.last_frame_number:
                raise AppError(ErrorCode.INVALID_FRAME, "Frame number must increase (old or replayed frame)")
            now = utcnow()
            if st.last_frame_at is not None and (now - st.last_frame_at).total_seconds() > self.s.max_frame_gap_s:
                self._fail(st, ErrorCode.CHALLENGE_FAILED)
                return self.describe(st, message="Frame stream interrupted")
            st.last_frame_number, st.last_frame_at = frame_number, now
            if st.status == "CREATED":
                st.status = "IN_PROGRESS"
                self.sessions_repo.update_status(st.session_id, "IN_PROGRESS")
            return self._step(st, frame_number, frame, now)

    def _step(self, st: SessionState, frame_number: int, frame: np.ndarray, now: datetime) -> dict:
        action = st.current_action
        passive = st.phase == "PASSIVE"
        need_eyes = passive or (st.evaluator is not None and st.evaluator.needs_eyes())
        need_embedding = passive or action == Action.CENTER or (
            st.session_type == ENROLLMENT and action in SIDE_POSES)
        fa = self.analyzer.analyze(frame, require_frontal=passive or action == Action.CENTER,
                                   need_eyes=need_eyes, need_embedding=need_embedding)

        if fa.error == ErrorCode.MULTIPLE_FACES:
            self._fail(st, ErrorCode.MULTIPLE_FACES)
            return self.describe(st, fa, "More than one face in view")
        if fa.error == ErrorCode.NO_FACE:
            return self._maybe_timeout(st, now, fa, "No face detected")

        # Continuity: the tracked face may not jump (guards against swapping the presented face).
        center = (fa.face.bbox[:2] + fa.face.bbox[2:]) / 2
        if st.last_center is not None and \
                np.linalg.norm(center - st.last_center) > self.s.max_face_jump * fa.face.width:
            self._fail(st, ErrorCode.CHALLENGE_FAILED)
            return self.describe(st, fa, "Face position changed abruptly")
        st.last_center = center

        if fa.liveness_score is not None:
            stage = "PASSIVE" if passive else "ACTIVE"
            st.all_scores.append(fa.liveness_score)
            self.sessions_repo.add_liveness_event(st.session_id, frame_number, fa.liveness_score,
                                                  fa.liveness_score >= self.s.liveness_threshold, stage)

        if fa.error == ErrorCode.LOW_FACE_QUALITY:
            return self._maybe_timeout(st, now, fa, f"Low quality: {fa.quality.quality_reason}")

        if passive:
            return self._passive_step(st, fa, now)
        return self._active_step(st, fa, now)

    def _maybe_timeout(self, st: SessionState, now: datetime, fa, message: str) -> dict:
        if st.phase == "ACTIVE" and (now - st.action_started_at).total_seconds() > self.s.action_timeout_s:
            self._fail(st, ErrorCode.CHALLENGE_FAILED)
            return self.describe(st, fa, "Challenge action timed out")
        return self.describe(st, fa, message)

    def _passive_step(self, st: SessionState, fa, now: datetime) -> dict:
        if fa.liveness_score is None:
            return self.describe(st, fa, "Move closer to the camera")
        st.passive_scores.append(fa.liveness_score)
        st.baseline_obs.append((fa.quality.yaw, fa.quality.pitch, fa.eye_openness or 0.0))
        st.center_samples.append(Sample(fa.embedding, "CENTER", fa.quality.blur_score))
        if len(st.passive_scores) < self.s.liveness_min_frames:
            return self.describe(st, fa, "Checking liveness...")

        result = self.analyzer.r.liveness.aggregate(st.passive_scores)
        if not result.is_live:
            self._fail(st, ErrorCode.LIVENESS_FAILED)
            return self.describe(st, fa, "Liveness check failed")
        st.liveness_score = result.score
        if not self.s.active_liveness_enabled:
            st.status, st.phase = "PASSED", "DONE"
            self.sessions_repo.update_status(st.session_id, "PASSED", challenge=st.challenge_json())
            return self.describe(st, fa, "Liveness passed. Finishing...")
        yaw, pitch, eyes = np.median(np.array(st.baseline_obs), axis=0)
        st.baseline = Baseline(float(yaw), float(pitch), float(eyes))
        st.phase = "ACTIVE"
        self._begin_action(st, now)
        return self.describe(st, fa, INSTRUCTIONS[st.current_action])

    def _begin_action(self, st: SessionState, now: datetime) -> None:
        st.action_started_at = now
        st.evaluator = ActionEvaluator(st.current_action, st.baseline, self.s)
        self.sessions_repo.update_status(st.session_id, "IN_PROGRESS", challenge=st.challenge_json())

    def _active_step(self, st: SessionState, fa, now: datetime) -> dict:
        action = st.current_action
        if (now - st.action_started_at).total_seconds() > self.s.action_timeout_s:
            self._fail(st, ErrorCode.CHALLENGE_FAILED)
            return self.describe(st, fa, "Challenge action timed out")
        done = st.evaluator.update(Observation(fa.quality.yaw, fa.quality.pitch, fa.eye_openness))
        if not done:
            return self.describe(st, fa, INSTRUCTIONS[action])

        if action in SIDE_POSES and st.session_type == ENROLLMENT and fa.embedding is not None:
            if abs(fa.quality.yaw - st.baseline.yaw) >= self.s.enrollment_side_yaw_min:
                st.side_samples.append(Sample(fa.embedding, SIDE_POSES[action], fa.quality.blur_score))
        if action == Action.CENTER:
            ref = self.analyzer.r.embedding.mean_embedding(np.array([x.embedding for x in st.center_samples]))
            sim = float(fa.embedding @ ref)
            if sim < self.consistency_threshold():
                log.info("session %s identity drift: sim=%.3f", st.session_id, sim)
                self._fail(st, ErrorCode.CHALLENGE_FAILED)
                return self.describe(st, fa, "Face changed during the session")
            st.final_samples.append(Sample(fa.embedding, "CENTER", fa.quality.blur_score))

        st.action_index += 1
        if st.action_index < len(st.actions):
            self._begin_action(st, now)
            return self.describe(st, fa, INSTRUCTIONS[st.current_action])

        # Whole-session passive check: every scored frame (passive + active) aggregated.
        result = self.analyzer.r.liveness.aggregate(st.all_scores)
        st.liveness_score = result.score
        if not result.is_live:
            self._fail(st, ErrorCode.LIVENESS_FAILED)
            return self.describe(st, fa, "Liveness check failed")
        st.status, st.phase = "PASSED", "DONE"
        self.sessions_repo.update_status(st.session_id, "PASSED", challenge=st.challenge_json())
        return self.describe(st, fa, "Liveness passed. Finishing...")

    # ------------------------------------------------------------------ complete
    def complete(self, session_id: uuid.UUID, session_type: str) -> dict:
        st = self._get(session_id)
        if st.session_type != session_type:
            raise AppError(ErrorCode.SESSION_STATE, "Wrong session type for this endpoint")
        with st.lock:
            self._check_expiry_for_complete(st)
            if st.status in ("CREATED", "IN_PROGRESS"):
                raise AppError(ErrorCode.SESSION_STATE, "Session has not finished the liveness challenge")
            if not self.sessions_repo.mark_completed(st.session_id):
                raise AppError(ErrorCode.SESSION_STATE, "Session already completed")
            if st.status != "PASSED":
                code = st.failure_code or ErrorCode.LIVENESS_FAILED
                result = {ErrorCode.SESSION_EXPIRED: "EXPIRED"}.get(code, code.value)
                self.sessions_repo.add_result(st.session_id, result, liveness=st.liveness_score)
                return {"session_id": str(st.session_id), "result": result, "error_code": code.value}
            if session_type == ENROLLMENT:
                return self._complete_enrollment(st)
            return self._complete_recognition(st)

    def _check_expiry_for_complete(self, st: SessionState) -> None:
        # A PASSED session may still be completed shortly after expiry of the challenge window,
        # but not indefinitely: allow at most one extra action timeout.
        grace = st.expires_at + timedelta(seconds=self.s.action_timeout_s)
        if st.status in ("CREATED", "IN_PROGRESS", "PASSED") and utcnow() > grace:
            if st.status != "PASSED":
                st.status = "EXPIRED"
                st.failure_code = ErrorCode.SESSION_EXPIRED
                self.sessions_repo.update_status(st.session_id, "EXPIRED", ErrorCode.SESSION_EXPIRED.value)
            raise AppError(ErrorCode.SESSION_EXPIRED, "Session expired")

    def _probe_embedding(self, st: SessionState) -> np.ndarray:
        embs = np.array([x.embedding for x in st.center_samples + st.final_samples])
        return self.analyzer.r.embedding.mean_embedding(embs)

    def _complete_recognition(self, st: SessionState) -> dict:
        thr = self.identity_threshold()
        probe = self._probe_embedding(st)
        matches = self.vectors.search(probe, self.meta, top_k=self.s.search_top_k)
        best = matches[0] if matches else None
        base = {"session_id": str(st.session_id), "liveness_score": round(st.liveness_score, 4),
                "threshold": thr}
        if best is None or best["similarity"] < thr:
            self.sessions_repo.add_result(st.session_id, "UNKNOWN", None, best["similarity"] if best else None,
                                          st.liveness_score, thr, self.meta.model_name, self.meta.model_version)
            return {**base, "result": "UNKNOWN", "similarity": round(best["similarity"], 4) if best else None}
        self.sessions_repo.add_result(st.session_id, "KNOWN", best["person_id"], best["similarity"],
                                      st.liveness_score, thr, self.meta.model_name, self.meta.model_version)
        return {**base, "result": "KNOWN", "similarity": round(best["similarity"], 4),
                "person": {"id": str(best["person_id"]), "name": best["name"], "external_id": best["external_id"]}}

    def _complete_enrollment(self, st: SessionState) -> dict:
        thr = self.identity_threshold()
        probe = self._probe_embedding(st)
        others = [m for m in self.vectors.search(probe, self.meta, top_k=self.s.search_top_k, only_active=False)
                  if m["person_id"] != st.person_id and m["similarity"] >= thr]
        if others:
            self.sessions_repo.add_result(st.session_id, "UNKNOWN", liveness=st.liveness_score)
            raise AppError(ErrorCode.INVALID_REQUEST,
                           "This face already matches another enrolled person; enrollment refused", 409)
        centers = sorted(st.center_samples, key=lambda x: x.quality, reverse=True)[:self.s.enrollment_center_samples]
        samples = centers + st.side_samples + st.final_samples
        for smp in samples:
            self.vectors.insert(st.person_id, smp.embedding, self.meta, smp.pose, smp.quality)
        self.people.set_status(st.person_id, "ACTIVE")
        self.sessions_repo.add_result(st.session_id, "ENROLLED", st.person_id, None, st.liveness_score, thr,
                                      self.meta.model_name, self.meta.model_version)
        return {"session_id": str(st.session_id), "result": "ENROLLED", "person_id": str(st.person_id),
                "embeddings_stored": len(samples), "poses": sorted({x.pose for x in samples}),
                "liveness_score": round(st.liveness_score, 4)}

    # ------------------------------------------------------------------ views
    def describe(self, st: SessionState, fa=None, message: str | None = None) -> dict:
        action = st.current_action
        out = {
            "session_id": str(st.session_id),
            "session_type": st.session_type,
            "status": st.status,
            "phase": st.phase,
            "current_action": action.value if action else None,
            "instruction": INSTRUCTIONS[action] if action else None,
            "completed_actions": st.action_index,
            "total_actions": len(st.actions),
            "passive_frames": len(st.passive_scores),
            "passive_frames_required": self.s.liveness_min_frames,
            "expires_at": st.expires_at.isoformat(),
            "error_code": st.failure_code.value if st.failure_code else None,
            "message": message,
        }
        if fa is not None:
            out["frame"] = {
                "face_count": fa.face_count,
                "frame_error": fa.error.value if fa.error else None,
                "quality": fa.quality.to_dict() if fa.quality else None,
                "liveness_frame_score": round(fa.liveness_score, 4) if fa.liveness_score is not None else None,
                "timings_ms": {k: round(v, 1) for k, v in fa.timings_ms.items()},
            }
        return out

    def status(self, session_id: uuid.UUID) -> dict:
        st = self._sessions.get(session_id)
        if st is not None:
            with st.lock:
                try:
                    self._check_expiry(st)
                except AppError:
                    pass
                return self.describe(st)
        row = self.sessions_repo.get(session_id)
        if row is None:
            raise AppError(ErrorCode.SESSION_NOT_FOUND, "Session not found")
        return {"session_id": str(row["session_id"]), "session_type": row["session_type"], "status": row["status"],
                "error_code": row["failure_code"], "expires_at": row["expires_at"].isoformat(),
                "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None}
