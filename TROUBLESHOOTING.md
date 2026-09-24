# Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `cv2.error: Unknown C++ exception from OpenCV code` inside `cv2.resize` | OpenCV's thread pool fails intermittently on this machine once ONNX Runtime is loaded. `build_registry` sets `cv2.setNumThreads(1)`. Custom scripts that call OpenCV before building the registry should do the same. |
| `Windows fatal exception: code 0x8007000e` printed during pytest | pytest's faulthandler printing a first-chance out-of-memory exception. It appeared while calibration, the frontend build and the tests ran at the same time on a 16 GB machine; the tests still passed. Close other heavy processes. |
| `NOT_CALIBRATED` (503) on session start | Run `evaluation/recognition/calibrate_threshold.py`. The config must name the currently loaded recognition model. |
| `/health` shows `database_ok: false` | `.env` credentials are wrong, the PostgreSQL service is stopped (`Get-Service postgresql-x64-18`), or pgvector is not installed (DATABASE.md) |
| `pgvector is not installed in this PostgreSQL server` | Run `scripts\install_pgvector.ps1` from an **elevated** PowerShell |
| `psql` not found | It is not on PATH. Use `"C:\Program Files\PostgreSQL\18\bin\psql.exe"` |
| Camera test: `camera 0 unavailable` | Another app is using the camera, or Windows privacy settings block it (Settings → Privacy → Camera → allow desktop apps). Try `--camera 1`. |
| LOOK_LEFT and LOOK_RIGHT seem swapped | The client sends mirrored frames. Send raw frames, or set `CAMERA_MIRRORED=true`. |
| Challenge actions time out | Low frame rate or small movements. Check `frame.timings_ms` in responses. Tune `YAW_DELTA`, `PITCH_DELTA` or `ACTION_TIMEOUT_S` in `.env` (and document the change in the experiment record). |
| Frequent `LOW_FACE_QUALITY` | The response's `quality.quality_reason` names the failing check. Thresholds are the `QUALITY_*` settings in `backend/app/core/config.py`. |
| `insightface` / `onnxruntime` wheels missing | Use Python 3.12 (uv), not the system 3.14 |
