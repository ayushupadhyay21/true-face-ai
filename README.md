# AI Face Liveness Research

A local-only research system that combines face recognition with liveness detection (presentation attack detection, PAD). It identifies a registered person only after passive and active liveness checks pass. This is a research prototype: **no claim is made that it cannot be spoofed** (see [SECURITY.md](SECURITY.md)).

```text
Camera -> SCRFD detection (exactly one face) -> quality -> passive PAD (Silent-Face, 5-frame mean)
       -> random active challenge (head turns / blink, then CENTER + same-person check)
       -> ArcFace embedding -> pgvector cosine search -> calibrated threshold -> KNOWN / UNKNOWN
```

Identity is searched only after liveness has passed. A failed liveness check never reveals an identity.

## Stack

| Layer | Technology |
|---|---|
| Models | InsightFace SCRFD-10GF, ArcFace R50, 2d106 landmarks; Silent-Face MiniFASNet (all ONNX Runtime, CPU) |
| Backend | Python 3.12, FastAPI, OpenCV |
| Database | PostgreSQL 18 + pgvector |
| Frontend | Angular 21 with browser camera APIs (getUserMedia) |

**Licenses:** the InsightFace weights are for **non-commercial research only** (see [LICENSES.md](LICENSES.md)).

## Quick start

See [SETUP.md](SETUP.md):

```powershell
cd backend;  ..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
cd frontend; npm start      # http://localhost:4200
```

## Documents

| File | Contents |
|---|---|
| [ENVIRONMENT.md](ENVIRONMENT.md) | Machine audit |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Components and pipeline order |
| [SETUP.md](SETUP.md) | Install and run |
| [MODEL_DOCUMENTATION.md](MODEL_DOCUMENTATION.md) | Model I/O, preprocessing, aggregation, versioning |
| [LICENSES.md](LICENSES.md) | Code, weight and dataset licenses |
| [DATASETS.md](DATASETS.md) | Data provenance and consent |
| [DATABASE.md](DATABASE.md) | Schema and pgvector |
| [API.md](API.md) | Endpoints and error codes |
| [EVALUATION.md](EVALUATION.md) | Measured results and how to reproduce them |
| [SECURITY.md](SECURITY.md) | Enforced rules and limitations |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Known problems and fixes |
