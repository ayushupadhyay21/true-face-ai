"""Shared helpers for evaluation scripts: import path, experiment records, hardware info."""
from __future__ import annotations

import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

EXPERIMENTS_DIR = ROOT / "evaluation" / "experiments"


def hardware() -> dict:
    import onnxruntime
    import psutil
    return {"platform": platform.platform(), "processor": platform.processor(),
            "logical_cpus": psutil.cpu_count(), "ram_gb": round(psutil.virtual_memory().total / 2**30, 1),
            "python": platform.python_version(), "onnxruntime": onnxruntime.__version__,
            "providers": onnxruntime.get_available_providers()}


def new_experiment_id(kind: str) -> str:
    return f"{kind}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def save_experiment(record: dict) -> Path:
    """Write an experiment record. Never overwrites: refuses if the id already exists."""
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPERIMENTS_DIR / f"{record['experiment_id']}.json"
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    return path
