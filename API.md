# API

Base URL: `http://localhost:8000` (local only). Interactive docs are at `/docs`, which FastAPI generates.

Every response uses the same envelope:

```json
{"ok": true, "data": { ... }, "error": null}
{"ok": false, "data": null, "error": {"code": "SESSION_EXPIRED", "message": "Session expired"}}
```

## Error codes

| Code | HTTP | Meaning |
|---|---|---|
| INVALID_REQUEST | 400/409/422 | Schema validation failed (unknown fields are rejected), duplicate external_id, or duplicate identity at enrollment |
| INVALID_FRAME | 400 | Undecodable, too large or tiny image, or a frame_number that is not increasing |
| PERSON_NOT_FOUND / SESSION_NOT_FOUND | 404 | Unknown id |
| SESSION_EXPIRED | 410 | Session lifetime exceeded |
| SESSION_STATE | 409 | Wrong step: frame after the session ended, complete before liveness finished, second completion, or wrong session type |
| NOT_CALIBRATED | 503 | No identity threshold for the loaded recognition model |
| MODEL_UNAVAILABLE / DATABASE_ERROR | 503 | Model file missing / DB unreachable |
| INTERNAL_ERROR | 500 | Unexpected; details only in `logs/backend.log` |

Session outcomes (`error_code` / `result`): NO_FACE (frame-level, the session waits), MULTIPLE_FACES, LOW_FACE_QUALITY (frame-level), LIVENESS_FAILED, CHALLENGE_FAILED, SESSION_EXPIRED, UNKNOWN, KNOWN, ENROLLED.

## Endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/health` | – | `{status, database, database_ok}` |
| GET | `/health/models` | – | Model names and versions, embedding dimension, preprocessing version, `identity_threshold`, `calibrated`, `liveness_threshold` |
| POST | `/api/person` | `{name, external_id?}` | Person (status `PENDING` until enrolled) |
| GET | `/api/person/{id}` | – | Person plus `embedding_count` |
| DELETE | `/api/person/{id}` | – | `{deleted}` (cascades to embeddings) |
| POST | `/api/enrollment/start` | `{person_id}` | SessionView |
| POST | `/api/enrollment/frame` | FrameSubmit | SessionView plus `frame` |
| POST | `/api/enrollment/complete` | `{session_id}` | `{result: "ENROLLED", embeddings_stored, poses, liveness_score}` or a failure result |
| POST | `/api/recognition/start` | – | SessionView |
| POST | `/api/recognition/frame` | FrameSubmit | SessionView plus `frame` |
| POST | `/api/recognition/complete` | `{session_id}` | `{result: KNOWN, person, similarity, threshold, liveness_score}`, `{result: UNKNOWN, similarity}`, or `{result: LIVENESS_FAILED/CHALLENGE_FAILED/MULTIPLE_FACES/EXPIRED, error_code}` |
| GET | `/api/recognition/{session_id}` | – | Session status plus result (the person name appears only for KNOWN) |
| GET | `/api/liveness/{session_id}` | – | Session status plus per-frame PAD `events` |

**FrameSubmit:** `{session_id, frame_number (int ≥ 0, strictly increasing), image_base64}`. The image is a JPEG or PNG, ≤ 1280 px and ≤ 2 MB, and may be a `data:` URL. Send the **raw, un-mirrored** camera frame, one request at a time.

**SessionView:** `session_id, session_type, status, phase (PASSIVE|ACTIVE|DONE), current_action, instruction, completed_actions, total_actions, passive_frames, passive_frames_required, expires_at, error_code, message`. Frame responses add `frame: {face_count, frame_error, quality{…, quality_reason}, liveness_frame_score, timings_ms}`.

## Typical recognition flow

```text
POST /api/recognition/start                    -> status CREATED
loop: POST /api/recognition/frame (n = 0, 1, 2 …) until status in PASSED | FAILED | EXPIRED
      show `instruction` to the user
POST /api/recognition/complete                 -> KNOWN / UNKNOWN / failure
```
