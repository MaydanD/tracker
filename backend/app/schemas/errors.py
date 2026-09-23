"""API error schemas: one consistent envelope for every failure response."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Machine-readable error payload."""

    code: str = Field(description="Stable identifier, e.g. 'not_found'.")
    message: str = Field(description="Human-readable explanation.")
    details: dict[str, Any] | None = Field(
        default=None, description="Optional structured context."
    )


class ErrorResponse(BaseModel):
    """Envelope returned by every error response, including validation errors."""

    error: ErrorDetail
