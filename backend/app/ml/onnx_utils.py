from __future__ import annotations

import hashlib
from pathlib import Path

import onnxruntime as ort

from app.core.errors import AppError, ErrorCode


def create_session(path: Path, providers: str, threads: int = 0) -> ort.InferenceSession:
    if not path.exists():
        raise AppError(ErrorCode.MODEL_UNAVAILABLE, f"Model file missing: {path.name}")
    opts = ort.SessionOptions()
    opts.log_severity_level = 3
    if threads > 0:
        opts.intra_op_num_threads = threads
    return ort.InferenceSession(str(path), sess_options=opts,
                                providers=[p.strip() for p in providers.split(",") if p.strip()])


def file_sha256_prefix(path: Path, n: int = 12) -> str:
    """Short content hash used as the model version (the files carry no version metadata)."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:n]
