# Backend

FastAPI and an ONNX Runtime (CPU) pipeline. The design is in [../ARCHITECTURE.md](../ARCHITECTURE.md), the endpoints in [../API.md](../API.md).

```powershell
# from backend/
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
..\.venv\Scripts\python.exe -m pytest            # unit + integration + e2e
..\.venv\Scripts\python.exe -m pytest tests/unit # no DB, fast
```

| Requirements file | Contents |
|---|---|
| `requirements.txt` | Runtime |
| `requirements-dev.txt` | Adds pytest, httpx, matplotlib |
| `requirements-convert.txt` | CPU torch + onnx, only for the one-time Silent-Face ONNX export |

Test layout:

| Folder | Contents |
|---|---|
| `tests/unit` | Models on LFW images, quality, alignment, challenge logic, metrics, and the session engine with in-memory fakes |
| `tests/integration` | `test_api.py` (real models, fake repositories); `test_database.py` (real PostgreSQL + pgvector, skipped without `.env` credentials) |
| `tests/e2e` | Baseline recognition on LFW, and a static-photo attack through the full API |
