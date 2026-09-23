"""Minimal, consistent API error handling.

Expected failures raise :class:`AppError` subclasses and are rendered as the
:class:`~app.schemas.errors.ErrorResponse` envelope. Unexpected failures are
logged with a traceback and answered with the same envelope shape, so the
frontend only ever has to understand one error format.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from app.core.logging import get_logger
from app.schemas.errors import ErrorDetail, ErrorResponse

logger = get_logger(__name__)

HTTP_ERROR_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    503: "service_unavailable",
}


class AppError(Exception):
    """Base class for expected, deliberately handled application errors."""

    code: str = "internal_error"
    status_code: int = 500
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details
        super().__init__(self.message)

    def to_response(self) -> ErrorResponse:
        return ErrorResponse(
            error=ErrorDetail(code=self.code, message=self.message, details=self.details)
        )


class DatabaseUnavailableError(AppError):
    """The SQLite database could not be reached."""

    code = "database_unavailable"
    status_code = 503
    message = "The database is currently unavailable."


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    payload = ErrorResponse(
        error=ErrorDetail(code=code, message=message, details=details)
    )
    return JSONResponse(
        status_code=status_code, content=payload.model_dump(exclude_none=True)
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the shared error handlers to ``app``."""

    @app.exception_handler(AppError)
    async def _handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        logger.warning("%s: %s", exc.code, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_response().model_dump(exclude_none=True),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            422,
            "validation_error",
            "The request payload is invalid.",
            {"errors": jsonable_encoder(exc.errors())},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = HTTP_ERROR_CODES.get(exc.status_code, "http_error")
        return _error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(
        _request: Request, exc: Exception
    ) -> JSONResponse:
        # Never swallow silently: log the traceback, answer with a generic body.
        logger.exception("Unhandled error: %s", exc)
        return _error_response(
            500, "internal_error", "An unexpected error occurred."
        )
