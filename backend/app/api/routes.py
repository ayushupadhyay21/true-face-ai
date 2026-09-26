from __future__ import annotations

import uuid

from fastapi import APIRouter, Response

from app.api.deps import get_container
from app.core.config import load_identity_threshold
from app.core.errors import AppError, ErrorCode
from app.schemas.api import EnrollmentStart, FrameSubmit, LiveFrame, LiveRef, PersonAssign, PersonCreate, SessionRef
from app.services.frame_analyzer import decode_frame
from app.services.session_engine import ENROLLMENT, RECOGNITION

router = APIRouter()


def ok(data) -> dict:
    return {"ok": True, "data": data, "error": None}


def _person_out(row: dict) -> dict:
    return {"id": str(row["id"]), "name": row["name"], "external_id": row["external_id"], "status": row["status"],
            "embedding_count": int(row.get("embedding_count") or 0),
            "created_at": row["created_at"].isoformat(), "updated_at": row["updated_at"].isoformat()}


# ------------------------------------------------------------------ health
@router.get("/health")
def health():
    c = get_container()
    try:
        db = c.db.ping()
        db_ok = db["pgvector"] is not None
    except AppError:
        db, db_ok = None, False
    return ok({"status": "ok" if db_ok else "degraded", "database": db, "database_ok": db_ok})


@router.get("/health/models")
def health_models():
    c = get_container()
    info = c.registry.describe()
    thr = load_identity_threshold(c.settings, c.engine.meta.model_name)
    return ok({"models": info, "identity_threshold": thr, "calibrated": thr is not None,
               "liveness_threshold": c.settings.liveness_threshold,
               "providers": c.settings.onnx_providers})


# ------------------------------------------------------------------ people
@router.post("/api/person", status_code=201)
def create_person(body: PersonCreate):
    return ok(_person_out({**get_container().people.create(body.name, body.external_id), "embedding_count": 0}))


@router.get("/api/person")
def list_people(status: str | None = None):
    return ok([_person_out(r) for r in get_container().people.list(status)])


@router.get("/api/person/{person_id}")
def get_person(person_id: uuid.UUID):
    row = get_container().people.get(person_id)
    if row is None:
        raise AppError(ErrorCode.PERSON_NOT_FOUND, "Person not found")
    return ok(_person_out(row))


@router.get("/api/person/{person_id}/snapshot")
def person_snapshot(person_id: uuid.UUID):
    row = get_container().people.get_snapshot(person_id)
    if row is None or row["snapshot"] is None:
        raise AppError(ErrorCode.PERSON_NOT_FOUND, "No snapshot for this person")
    return Response(content=bytes(row["snapshot"]), media_type=row["snapshot_mime"] or "image/jpeg")


@router.patch("/api/person/{person_id}")
def assign_person_name(person_id: uuid.UUID, body: PersonAssign):
    c = get_container()
    c.people.assign_name(person_id, body.name, body.external_id)
    return ok(_person_out(c.people.get(person_id)))


@router.delete("/api/person/{person_id}")
def delete_person(person_id: uuid.UUID):
    if not get_container().people.delete(person_id):
        raise AppError(ErrorCode.PERSON_NOT_FOUND, "Person not found")
    return ok({"deleted": str(person_id)})


# ------------------------------------------------------------------ sessions
def _frame(body: FrameSubmit, session_type: str):
    c = get_container()
    st = c.engine._get(body.session_id)
    if st.session_type != session_type:
        raise AppError(ErrorCode.SESSION_STATE, "Wrong session type for this endpoint")
    try:
        data = body.image_bytes()
    except ValueError as e:
        raise AppError(ErrorCode.INVALID_FRAME, str(e)) from e
    frame = decode_frame(data, c.settings)
    return ok(c.engine.process_frame(body.session_id, body.frame_number, frame))  # frame discarded after use


@router.post("/api/enrollment/start", status_code=201)
def enrollment_start(body: EnrollmentStart):
    return ok(get_container().engine.start(ENROLLMENT, body.person_id))


@router.post("/api/enrollment/frame")
def enrollment_frame(body: FrameSubmit):
    return _frame(body, ENROLLMENT)


@router.post("/api/enrollment/complete")
def enrollment_complete(body: SessionRef):
    return ok(get_container().engine.complete(body.session_id, ENROLLMENT))


@router.post("/api/recognition/start", status_code=201)
def recognition_start():
    return ok(get_container().engine.start(RECOGNITION))


@router.post("/api/recognition/frame")
def recognition_frame(body: FrameSubmit):
    return _frame(body, RECOGNITION)


@router.post("/api/recognition/complete")
def recognition_complete(body: SessionRef):
    return ok(get_container().engine.complete(body.session_id, RECOGNITION))


@router.get("/api/recognition/{session_id}")
def recognition_status(session_id: uuid.UUID):
    c = get_container()
    out = c.engine.status(session_id)
    res = c.sessions.get_result(session_id)
    if res is not None:
        out["result"] = res["result"]
        if res["result"] == "KNOWN" and res["person_id"]:
            person = c.people.get(res["person_id"])
            out["person"] = {"id": str(res["person_id"]), "name": person["name"] if person else None}
    return ok(out)


@router.get("/api/liveness/{session_id}")
def liveness_status(session_id: uuid.UUID):
    c = get_container()
    out = c.engine.status(session_id)
    events = c.sessions.liveness_events(session_id)
    out["events"] = [{"frame_number": e["frame_number"], "score": round(e["score"], 4), "prediction": e["prediction"],
                      "stage": e["stage"]} for e in events]
    return ok(out)


# ------------------------------------------------------------------ live multi-face mode
def _live():
    c = get_container()
    if c.live is None:
        raise AppError(ErrorCode.MODEL_UNAVAILABLE, "Live mode unavailable")
    return c


@router.post("/api/live/start", status_code=201)
def live_start():
    return ok(_live().live.start())


@router.post("/api/live/frame")
def live_frame(body: LiveFrame):
    c = _live()
    try:
        data = body.image_bytes()
    except ValueError as e:
        raise AppError(ErrorCode.INVALID_FRAME, str(e)) from e
    frame = decode_frame(data, c.settings)
    return ok(c.live.process_frame(body.live_id, body.frame_number, frame))  # frame discarded after use


@router.post("/api/live/stop")
def live_stop(body: LiveRef):
    return ok(_live().live.stop(body.live_id))
