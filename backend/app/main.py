"""FastAPI entry point (local research server).

Run from backend/:  python -m uvicorn app.main:app --reload
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import setup_logging

settings = get_settings()
setup_logging(settings)
log = logging.getLogger("app")

app = FastAPI(title="Face Liveness Research API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
                   allow_methods=["GET", "POST", "DELETE"], allow_headers=["Content-Type"])
app.include_router(router)


def _err(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    error = {"code": code, "message": message}
    if details:
        error["details"] = details
    return JSONResponse(status_code=status, content={"ok": False, "data": None, "error": error})


@app.exception_handler(AppError)
async def app_error(_: Request, exc: AppError):
    return _err(exc.status, exc.code.value, exc.message, exc.details)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    fields = ", ".join(".".join(str(p) for p in e["loc"][1:]) or "body" for e in exc.errors())
    return _err(422, ErrorCode.INVALID_REQUEST.value, f"Invalid request fields: {fields}")


@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, exc: StarletteHTTPException):
    return _err(exc.status_code, ErrorCode.INVALID_REQUEST.value, str(exc.detail))


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s %s", request.method, request.url.path)  # details stay in local log
    return _err(500, ErrorCode.INTERNAL_ERROR.value, "Internal error")
