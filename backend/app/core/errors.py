"""Error codes shared by the pipeline and the API."""
from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    NO_FACE = "NO_FACE"
    MULTIPLE_FACES = "MULTIPLE_FACES"
    LOW_FACE_QUALITY = "LOW_FACE_QUALITY"
    LIVENESS_FAILED = "LIVENESS_FAILED"
    CHALLENGE_FAILED = "CHALLENGE_FAILED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    SESSION_STATE = "SESSION_STATE"
    UNKNOWN_PERSON = "UNKNOWN_PERSON"
    PERSON_NOT_FOUND = "PERSON_NOT_FOUND"
    INVALID_FRAME = "INVALID_FRAME"
    INVALID_REQUEST = "INVALID_REQUEST"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    NOT_CALIBRATED = "NOT_CALIBRATED"
    DATABASE_ERROR = "DATABASE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


HTTP_STATUS = {
    ErrorCode.INVALID_FRAME: 400,
    ErrorCode.INVALID_REQUEST: 400,
    ErrorCode.SESSION_NOT_FOUND: 404,
    ErrorCode.PERSON_NOT_FOUND: 404,
    ErrorCode.SESSION_EXPIRED: 410,
    ErrorCode.SESSION_STATE: 409,
    ErrorCode.MODEL_UNAVAILABLE: 503,
    ErrorCode.NOT_CALIBRATED: 503,
    ErrorCode.DATABASE_ERROR: 503,
    ErrorCode.INTERNAL_ERROR: 500,
}


class AppError(Exception):
    """Expected, user-facing error. `message` must never contain internal details."""

    def __init__(self, code: ErrorCode, message: str, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status or HTTP_STATUS.get(code, 422)
