# Local Setup (Windows)

These steps were verified on the audit machine (ENVIRONMENT.md). Everything runs locally: no Docker, no cloud services.

## 1. Python environment (Python 3.12 via uv)

The system Python is 3.14, which is too new for some ML wheels. uv installs a private 3.12 without touching the system Python.

```powershell
uv python install 3.12
uv venv .venv --python 3.12
uv pip install --python .venv -r backend/requirements-dev.txt
```

## 2. Models

The models are git-ignored. Download them and verify the SHA-256 values listed in LICENSES.md:

```powershell
Invoke-WebRequest https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip -OutFile $env:TEMP\buffalo_l.zip
Expand-Archive $env:TEMP\buffalo_l.zip $env:TEMP\buffalo_l
Copy-Item $env:TEMP\buffalo_l\det_10g.onnx models\detection\
Copy-Item $env:TEMP\buffalo_l\w600k_r50.onnx, $env:TEMP\buffalo_l\2d106det.onnx models\recognition\
$u = "https://github.com/minivision-ai/Silent-Face-Anti-Spoofing/raw/master/resources/anti_spoof_models"
Invoke-WebRequest "$u/2.7_80x80_MiniFASNetV2.pth" -OutFile models\liveness\2.7_80x80_MiniFASNetV2.pth
Invoke-WebRequest "$u/4_0_0_80x80_MiniFASNetV1SE.pth" -OutFile models\liveness\4_0_0_80x80_MiniFASNetV1SE.pth
# one-time ONNX export (installs CPU torch, about 200 MB)
uv pip install --python .venv -r backend/requirements-convert.txt
.venv\Scripts\python.exe training\scripts\export_silentface_onnx.py
```

## 3. Database

See [DATABASE.md](DATABASE.md). In short:

1. Run `scripts\install_pgvector.ps1` from an elevated PowerShell.
2. Copy `.env.example` to `.env` and set `POSTGRES_PASSWORD`.
3. Run `.venv\Scripts\python.exe scripts\setup_database.py`.

## 4. Threshold calibration (needs LFW, see DATASETS.md)

```powershell
.venv\Scripts\python.exe evaluation\recognition\calibrate_threshold.py --target-far 0.001
```

This writes `evaluation/recognition/threshold_config.json`. The backend refuses to start sessions without it.

## 5. Run

```powershell
# backend (from backend/)
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# frontend (second terminal, from frontend/)
cd frontend
npm install
npm start          # http://localhost:4200
```

## 6. Tests and checks

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest              # DB tests skip unless .env has DB credentials
..\.venv\Scripts\python.exe ..\scripts\camera_test.py            # webcam window, q to quit
..\.venv\Scripts\python.exe ..\evaluation\performance\benchmark.py --n 100
```
