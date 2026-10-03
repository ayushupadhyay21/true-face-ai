"""Central configuration.

Every threshold used by the pipeline lives here, with a note on where the default
comes from. Values can be overridden through environment variables or the project
`.env` file (field name in upper case, e.g. QUALITY_MIN_FACE_SIZE=100).

The identity threshold is NOT set here by hand: it is read from the calibration file
written by evaluation/recognition/calibrate_threshold.py (see EVALUATION.md).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    # --- Database -------------------------------------------------------------
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "face_liveness_research"
    postgres_user: str = "face_research"
    postgres_password: str = ""

    # --- Paths / runtime ----------------------------------------------------------
    models_dir: Path = PROJECT_ROOT / "models"
    onnx_providers: str = "CPUExecutionProvider"
    onnx_threads: int = 0  # 0 = let ONNX Runtime decide
    store_raw_frames: bool = False  # privacy default: frames are never written to disk
    log_level: str = "INFO"
    log_dir: Path = PROJECT_ROOT / "logs"

    # --- Model files --------------------------------------------------------------
    detector_model: str = "detection/det_10g.onnx"
    recognizer_model: str = "recognition/w600k_r50.onnx"
    landmark106_model: str = "recognition/2d106det.onnx"
    liveness_models: str = "liveness/2.7_80x80_MiniFASNetV2.onnx,liveness/4_0_0_80x80_MiniFASNetV1SE.onnx"

    # --- Detection ------------------------------------------------------------------
    # SCRFD reference implementation uses det_thresh=0.5 and nms_thresh=0.4 (insightface scrfd.py).
    det_input_size: int = 640
    det_score_threshold: float = 0.5
    det_nms_threshold: float = 0.4
    # Faces smaller than this (in px, shorter bbox side) are ignored when COUNTING faces, so
    # tiny background detections do not trigger MULTIPLE_FACES. Kept well below quality_min_face_size.
    det_min_count_face_size: int = 40

    # --- Quality (heuristic defaults, tune with evaluation data) --------------------
    quality_min_face_size: int = 80  # ArcFace input is 112 px; faces much smaller get upscaled heavily
    quality_min_det_score: float = 0.6
    quality_min_blur: float = 60.0  # variance of Laplacian on the 112x112 aligned crop
    quality_min_brightness: float = 50.0  # mean gray level 0..255 of the face crop
    quality_max_brightness: float = 210.0
    quality_min_contrast: float = 20.0  # std of gray level of the face crop
    quality_max_yaw: float = 0.35  # |yaw proxy| (see quality/service.py) allowed for CENTER frames
    quality_max_pitch: float = 0.35
    quality_max_landmark_outside: float = 0.0  # fraction of 5 landmarks allowed outside bbox

    # --- Passive liveness -----------------------------------------------------------
    # Upstream Silent-Face decides "real" when argmax of the fused softmax is class 1.
    # We threshold the fused real-class probability instead so the operating point can be tuned.
    liveness_threshold: float = 0.5
    liveness_min_frames: int = 5  # frames aggregated in the passive phase
    liveness_min_face_size: int = 60

    # --- Active liveness ------------------------------------------------------------------
    active_liveness_enabled: bool = True
    # Live View's own switch (separate from the session flag above): a silent, blink-only check
    # per track before it is ever named -- no on-screen prompt, no session lifecycle. Blink is
    # the only pool action that happens on its own within a few seconds without being asked; a
    # deliberate head-turn does not, so it is never used here (see live_tracker.py).
    live_active_liveness_enabled: bool = True
    challenge_length: int = 3  # random actions per session (a final CENTER is always appended)
    camera_mirrored: bool = False  # clients must send raw (un-mirrored) frames unless this is set
    challenge_timeout_s: float = 60.0  # whole session lifetime
    action_timeout_s: float = 12.0  # time allowed for each single action
    # Head-turn thresholds are relative to the baseline pose measured in the passive phase.
    yaw_delta: float = 0.25
    pitch_delta: float = 0.18
    center_tolerance: float = 0.12
    # Blink: eye-openness ratio must drop below closed_ratio * baseline, then recover above open_ratio * baseline.
    blink_closed_ratio: float = 0.65
    blink_open_ratio: float = 0.85
    # Frames of the same session must show the same person: cosine similarity between the
    # passive-phase embedding and the final CENTER embedding. Defaults to the calibrated identity
    # threshold when unset (None).
    session_consistency_threshold: float | None = None
    # Max bbox centre jump between consecutive frames, as a fraction of face width. Guards against
    # swapping the presented face mid-session.
    max_face_jump: float = 0.8
    max_frame_gap_s: float = 3.0

    # --- Enrollment ------------------------------------------------------------------------
    enrollment_center_samples: int = 3
    enrollment_side_yaw_min: float = 0.15  # side samples need at least this yaw change from baseline

    # --- Recognition -----------------------------------------------------------------------
    calibration_file: Path = PROJECT_ROOT / "evaluation" / "recognition" / "threshold_config.json"
    identity_threshold_override: float | None = Field(default=None, description="Research use only")
    search_top_k: int = 5

    # --- Live mode: unknown-face bucketing ---------------------------------------------------
    # When a live-mode track has no match in the gallery, auto-create an UNASSIGNED person with
    # a small aligned-crop snapshot (not the raw frame), so an operator can name them later.
    live_auto_enroll_unknown: bool = True

    # --- API -------------------------------------------------------------------------------
    max_frame_bytes: int = 2_000_000
    max_frame_side: int = 1280
    cors_origins: str = "http://localhost:4200"

    @property
    def database_url(self) -> str:
        return (f"host={self.postgres_host} port={self.postgres_port} dbname={self.postgres_db} "
                f"user={self.postgres_user} password={self.postgres_password}")

    def model_path(self, rel: str) -> Path:
        return self.models_dir / rel


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_identity_threshold(settings: Settings, model_name: str) -> float | None:
    """Return the calibrated cosine threshold for `model_name`, or None if not calibrated.

    Refuses thresholds calibrated for a different model (never mix thresholds across models).
    """
    if settings.identity_threshold_override is not None:
        return settings.identity_threshold_override
    path = settings.calibration_file
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("model_name") != model_name:
        return None
    return float(data["threshold"])
