"""Live multi-face mode: detect every face in real time, track it, and label it.

Unlike the verification sessions (session_engine.py), several faces may be in view. Each
face is tracked across frames (greedy IoU matching), and each track gets its own rules:

  * Passive liveness per track: frame scores are kept over a rolling window. A track becomes
    LIVE once at least LIVE_MIN_FRAMES scores exist and their mean is >= threshold.
    Otherwise it is SPOOF.
  * Identity is computed only for LIVE tracks with good quality. Up to LIVE_MAX_EMBEDDINGS
    embeddings are averaged per track, then cached, which keeps CPU cost bounded.
  * A name is returned only when the track is LIVE and similarity >= the calibrated threshold.
    It is hidden again if the track's liveness drops.
  * If a new embedding does not match the track's own mean embedding, a different face
    probably took the tracked position, so the track is reset.
  * If `live_auto_enroll_unknown` is on (default): a LIVE track with no gallery match gets its
    own UNASSIGNED person row, with a small aligned-crop snapshot (never the raw frame) so an
    operator can name them later, Google-Photos-style. Seeing the same unnamed face again reuses
    that same person row instead of creating a new one, because the search below is not
    restricted to ACTIVE people.

No active challenge runs in this mode, so it is weaker against video replay than a
verification session (see SECURITY.md). Frames are kept in memory only; the only thing
ever written to the database here is an unassigned person's embedding and crop.
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field

import cv2
import numpy as np

from app.core.config import Settings, load_identity_threshold
from app.core.errors import AppError, ErrorCode
from app.db.repositories import EmbeddingMeta
from app.ml.base import DetectedFace

LIVE_WINDOW = 10  # rolling window of passive scores per track
LIVE_MAX_EMBEDDINGS = 5  # embeddings averaged per track before the identity is cached
TRACK_IOU = 0.3  # min IoU to continue a track
TRACK_MAX_MISSED = 5  # frames a track survives without a matching detection
SESSION_IDLE_S = 60.0  # live sessions without frames for this long are dropped
MAX_LIVE_SESSIONS = 8


def iou(a: np.ndarray, b: np.ndarray) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return float(inter / union) if union > 0 else 0.0


@dataclass
class Track:
    track_id: int
    bbox: np.ndarray
    scores: deque = field(default_factory=lambda: deque(maxlen=LIVE_WINDOW))
    embeddings: list[np.ndarray] = field(default_factory=list)
    match: dict | None = None  # best gallery match for the mean embedding, any status
    own_person_id: uuid.UUID | None = None  # the ACTIVE match, or an UNASSIGNED person we bucketed this face into
    missed: int = 0

    def reset_identity(self) -> None:
        self.embeddings.clear()
        self.match = None
        self.own_person_id = None


@dataclass
class LiveSession:
    live_id: uuid.UUID
    last_frame_number: int = -1
    last_seen: float = field(default_factory=time.monotonic)
    tracks: list[Track] = field(default_factory=list)
    next_track_id: int = 1
    lock: threading.Lock = field(default_factory=threading.Lock)


class LiveTracker:
    def __init__(self, settings: Settings, registry, people, vectors, meta: EmbeddingMeta):
        self.s = settings
        self.r = registry
        self.people = people
        self.vectors = vectors
        self.meta = meta
        self._sessions: dict[uuid.UUID, LiveSession] = {}
        self._lock = threading.Lock()

    def _threshold(self) -> float:
        thr = load_identity_threshold(self.s, self.meta.model_name)
        if thr is None:
            raise AppError(ErrorCode.NOT_CALIBRATED, "Recognition threshold not calibrated for the current model")
        return thr

    def start(self) -> dict:
        self._threshold()
        now = time.monotonic()
        with self._lock:
            for k in [k for k, v in self._sessions.items() if now - v.last_seen > SESSION_IDLE_S]:
                del self._sessions[k]
            if len(self._sessions) >= MAX_LIVE_SESSIONS:
                raise AppError(ErrorCode.SESSION_STATE, "Too many live sessions open; stop one first", 429)
            ls = LiveSession(uuid.uuid4())
            self._sessions[ls.live_id] = ls
        return {"live_id": str(ls.live_id)}

    def stop(self, live_id: uuid.UUID) -> dict:
        with self._lock:
            existed = self._sessions.pop(live_id, None) is not None
        return {"stopped": existed}

    def process_frame(self, live_id: uuid.UUID, frame_number: int, frame: np.ndarray) -> dict:
        ls = self._sessions.get(live_id)
        if ls is None:
            raise AppError(ErrorCode.SESSION_NOT_FOUND, "Live session not found or expired")
        with ls.lock:
            if frame_number <= ls.last_frame_number:
                raise AppError(ErrorCode.INVALID_FRAME, "Frame number must increase")
            ls.last_frame_number = frame_number
            ls.last_seen = time.monotonic()
            return self._step(ls, frame)

    # ------------------------------------------------------------------ internals
    def _step(self, ls: LiveSession, frame: np.ndarray) -> dict:
        thr = self._threshold()
        t0 = time.perf_counter()
        faces = [f for f in self.r.detection.detector.detect(frame) if f.size >= self.s.det_min_count_face_size]
        t_det = (time.perf_counter() - t0) * 1000
        assigned = self._associate(ls, faces)

        h, w = frame.shape[:2]
        out = []
        for face, track in assigned:
            out.append(self._update_track(track, frame, face, thr, w, h))
        return {"frame_width": w, "frame_height": h, "faces": out, "face_count": len(out),
                "threshold": round(thr, 4), "timings_ms": {"detection": round(t_det, 1),
                                                           "total": round((time.perf_counter() - t0) * 1000, 1)}}

    def _associate(self, ls: LiveSession, faces: list[DetectedFace]) -> list[tuple[DetectedFace, Track]]:
        pairs = sorted(((iou(f.bbox, t.bbox), i, j) for i, f in enumerate(faces) for j, t in enumerate(ls.tracks)),
                       reverse=True)
        used_f, used_t, assigned = set(), set(), []
        for score, i, j in pairs:
            if score < TRACK_IOU or i in used_f or j in used_t:
                continue
            used_f.add(i), used_t.add(j)
            ls.tracks[j].bbox, ls.tracks[j].missed = faces[i].bbox, 0
            assigned.append((faces[i], ls.tracks[j]))
        for j, t in enumerate(ls.tracks):
            if j not in used_t:
                t.missed += 1
        for i, f in enumerate(faces):
            if i not in used_f:
                t = Track(ls.next_track_id, f.bbox)
                ls.next_track_id += 1
                ls.tracks.append(t)
                assigned.append((f, t))
        ls.tracks = [t for t in ls.tracks if t.missed <= TRACK_MAX_MISSED]
        return assigned

    def _update_track(self, track: Track, frame: np.ndarray, face: DetectedFace, thr: float, w: int, h: int) -> dict:
        s = self.s
        box = [round(float(face.bbox[0]) / w, 4), round(float(face.bbox[1]) / h, 4),
               round(float(face.bbox[2]) / w, 4), round(float(face.bbox[3]) / h, 4)]
        base = {"track_id": track.track_id, "bbox": box}
        if face.size < s.liveness_min_face_size:
            return {**base, "state": "TOO_SMALL", "label": "Move closer", "liveness_score": None,
                    "name": None, "person_id": None, "similarity": None}

        track.scores.append(self.r.liveness.frame_score(frame, face))
        mean = float(np.mean(track.scores))
        if len(track.scores) < s.liveness_min_frames:
            return {**base, "state": "CHECKING", "label": "Checking…", "liveness_score": round(mean, 4),
                    "name": None, "person_id": None, "similarity": None}
        if mean < s.liveness_threshold:
            track.reset_identity()  # never reveal (or keep) an identity for a failing track
            return {**base, "state": "SPOOF", "label": "Spoof", "liveness_score": round(mean, 4),
                    "name": None, "person_id": None, "similarity": None}

        if len(track.embeddings) < LIVE_MAX_EMBEDDINGS:
            aligned = self.r.alignment.align(frame, face.landmarks)
            q = self.r.quality.evaluate(face, aligned, require_frontal=True)
            if q.valid:
                emb = self.r.embedding.embed_one(aligned)
                if track.embeddings:
                    ref = self.r.embedding.mean_embedding(np.array(track.embeddings))
                    if float(emb @ ref) < thr:  # a different face took over this track position
                        track.reset_identity()
                track.embeddings.append(emb)
                if track.own_person_id is None:  # already identified: no need to re-query the DB every frame
                    probe = self.r.embedding.mean_embedding(np.array(track.embeddings))
                    # Not restricted to ACTIVE: an UNASSIGNED person seen again reuses their own row.
                    matches = self.vectors.search(probe, self.meta, top_k=1, only_active=False)
                    track.match = matches[0] if matches else None
                    if track.match is not None and track.match["similarity"] >= thr:
                        track.own_person_id = track.match["person_id"]
                    elif self.s.live_auto_enroll_unknown and track.own_person_id is None:
                        track.match = self._create_unknown(probe, aligned)
                        track.own_person_id = track.match["person_id"]

        m = track.match
        if m is not None and m["similarity"] >= thr and m["status"] == "ACTIVE":
            return {**base, "state": "KNOWN", "label": m["name"], "liveness_score": round(mean, 4),
                    "name": m["name"], "person_id": str(m["person_id"]), "similarity": round(m["similarity"], 4)}
        if track.own_person_id is not None:
            return {**base, "state": "UNASSIGNED", "label": m["name"] if m else None,
                    "liveness_score": round(mean, 4), "name": None, "person_id": str(track.own_person_id),
                    "similarity": round(m["similarity"], 4) if m else None}
        label = "Unknown" if track.embeddings else "Look at the camera"
        return {**base, "state": "UNKNOWN" if track.embeddings else "LIVE", "label": label,
                "liveness_score": round(mean, 4), "name": None, "person_id": None,
                "similarity": round(m["similarity"], 4) if m else None}

    def _create_unknown(self, probe: np.ndarray, aligned: np.ndarray) -> dict:
        """Bucket a LIVE, unmatched face under a new UNASSIGNED person (crop, never the raw frame)."""
        ok, buf = cv2.imencode(".jpg", aligned)
        snapshot = buf.tobytes() if ok else None
        person = self.people.create_unassigned(snapshot, "image/jpeg" if ok else None)
        self.vectors.insert(person["id"], probe, self.meta, "CENTER", None)
        return {"person_id": person["id"], "name": person["name"], "external_id": person["external_id"],
                "status": "UNASSIGNED", "similarity": 1.0, "matched_embeddings": 1}
