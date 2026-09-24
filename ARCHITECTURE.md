# Architecture

```text
Angular (localhost:4200)                          FastAPI (localhost:8000)                      PostgreSQL 18 + pgvector
 getUserMedia -> canvas (raw, un-mirrored)   POST /api/*/frame (base64 JPEG)
 one frame at a time, ~120 ms gap  ───────────────►  routes.py ──► SessionEngine ──► FrameAnalyzer ──► ModelRegistry (ONNX, CPU)
                                                          │               │
                                                          │               └── passive scores, status ──► recognition_sessions, liveness_events
                                                          └── complete() ── VectorSearchService ──► face_embeddings (cosine, <=>)
                                                                                                     recognition_results
```

## Backend layout (`backend/app`)

| Package | Responsibility |
|---|---|
| `core/` | `config.py` holds all thresholds and settings (overridable via `.env`) and loads the calibrated threshold. `errors.py` defines error codes and `AppError`. `logging.py` handles local file logging. |
| `ml/base.py` | Interfaces `FaceDetector`, `FaceRecognizer`, `LivenessDetector` and data types `DetectedFace`, `LivenessResult`, `ModelInfo` |
| `ml/detection/` | `SCRFDDetector` and `FaceDetectionService` (the exactly-one-face policy) |
| `ml/quality/` | `FaceQualityService`: size, detector confidence, landmarks, brightness, contrast, blur, pose |
| `ml/preprocessing/` | `FaceAlignmentService` (ArcFace 5-point similarity alignment) and `Landmark106` (eye openness) |
| `ml/recognition/` | `ArcFaceRecognizer` and `FaceEmbeddingService` |
| `ml/liveness/` | `SilentFaceLivenessDetector` (per-frame score plus temporal mean) |
| `ml/registry.py` | Builds all models once per process |
| `services/frame_analyzer.py` | Runs the per-frame steps in order and records timings |
| `services/challenge.py` | Random action sequence (CSPRNG) and per-action evaluators |
| `services/session_engine.py` | Session state machine for enrollment and recognition, plus all security rules |
| `db/` | `Database` (psycopg 3 plus pgvector), migrations, repositories, `VectorSearchService` |
| `api/` | Routes, dependency container, response envelope |

## Verification pipeline (order is fixed)

```text
frame ─► detect (0: wait | 2+: FAIL MULTIPLE_FACES) ─► continuity check (face may not jump)
      ─► passive PAD frame score (stored in liveness_events)
      ─► align ─► quality (invalid: feedback, frame not counted)
PASSIVE phase: 5 good frontal frames ─► mean PAD >= threshold? else FAIL LIVENESS_FAILED
               baseline yaw / pitch / eye openness = median of those frames
               embeddings computed but NOT searched
ACTIVE phase:  random actions (3 from LOOK_LEFT/RIGHT/UP/DOWN/BLINK, no repeats) + CENTER
               each action: 12 s timeout; head turns must hold 2 consecutive frames
               CENTER: embedding must match passive embedding (>= identity threshold) else FAIL
               end: mean PAD over ALL session frames >= threshold? else FAIL LIVENESS_FAILED
status PASSED ─► /complete ─► mean embedding ─► pgvector top-k ─► best >= threshold ? KNOWN : UNKNOWN
```

Enrollment uses the same engine. Its challenge always contains LOOK_LEFT and LOOK_RIGHT, at random positions. `/enrollment/complete` stores these embeddings:

- the 3 sharpest CENTER samples
- the LEFT and RIGHT samples, taken only when yaw changed by at least 0.15 from baseline
- the final CENTER sample

It refuses to enroll a face that already matches another enrolled person.

## Model abstraction

Services depend on the interfaces in `ml/base.py`. To try another detector, recognizer or PAD model, implement the interface and change `ml/registry.py`. Embeddings are tagged with model name, version, dimension and preprocessing version, so embeddings from different models are never compared.

## State

- The runtime session state (challenge progress, buffers) lives in process memory. The server is single-process and local.
- Session status, the challenge JSON, liveness events and results are persisted.
- If the server restarts, in-progress sessions end: new frames for them get `SESSION_NOT_FOUND`.
- Raw frames are decoded in memory and discarded after processing. They are never written to disk.

## Frontend

The Angular app lives in `frontend/` (see `frontend/README.md`):

- **CameraService:** getUserMedia, device selection, raw canvas capture.
- **ApiService:** typed calls, envelope error mapping.
- **Pages:** enrollment and recognition. Each runs a sequential frame loop and calls `/complete` once the status is final.
