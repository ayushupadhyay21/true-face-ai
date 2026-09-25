from __future__ import annotations

import base64
import binascii
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PersonCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    external_id: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v


class PersonOut(BaseModel):
    id: uuid.UUID
    name: str
    external_id: str | None
    status: str
    embedding_count: int = 0
    created_at: str
    updated_at: str


class EnrollmentStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    person_id: uuid.UUID


class SessionRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: uuid.UUID


class FrameSubmit(BaseModel):
    """One camera frame, JPEG or PNG, base64 encoded (optionally as a data: URL)."""
    model_config = ConfigDict(extra="forbid")
    session_id: uuid.UUID
    frame_number: int = Field(ge=0, le=100_000)
    image_base64: str = Field(min_length=100, max_length=3_000_000)

    def image_bytes(self) -> bytes:
        data = self.image_base64
        if data.startswith("data:"):
            data = data.split(",", 1)[-1]
        try:
            return base64.b64decode(data, validate=True)
        except (binascii.Error, ValueError) as e:
            raise ValueError("image_base64 is not valid base64") from e


class LiveRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    live_id: uuid.UUID


class LiveFrame(FrameSubmit):
    """Frame for live multi-face mode (same image rules as FrameSubmit)."""
    session_id: uuid.UUID | None = None  # unused; live frames are keyed by live_id
    live_id: uuid.UUID


class ErrorBody(BaseModel):
    code: str
    message: str


class Envelope(BaseModel):
    """Every response uses this shape: {"ok": bool, "data": ..., "error": {...} | null}."""
    ok: bool
    data: dict | list | None = None
    error: ErrorBody | None = None
