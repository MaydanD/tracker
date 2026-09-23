"""Area schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.db.models import Area
from app.domain.areas import NAME_MAX_LENGTH

# Format-level validation (name emptiness, hex colour) lives in ``app.domain`` so
# a single place decides what a valid area is; these schemas only describe types
# and shape.


class AreaCreate(BaseModel):
    """Payload for creating an area."""

    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    color: str | None = Field(
        default=None, description="Hex colour such as #4a7cc7."
    )


class AreaUpdate(BaseModel):
    """Partial update: send the fields that change."""

    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX_LENGTH)
    color: str | None = None

    @model_validator(mode="after")
    def _require_something_to_change(self) -> AreaUpdate:
        if self.name is None and self.color is None:
            raise ValueError("Provide a name or a colour to update.")
        return self


class AreaRead(BaseModel):
    """An area as returned by the API."""

    id: int
    name: str
    color: str
    is_archived: bool
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, area: Area) -> AreaRead:
        return cls(
            id=area.id,
            name=area.name,
            color=area.color,
            is_archived=area.is_archived,
            archived_at=area.archived_at,
            created_at=area.created_at,
            updated_at=area.updated_at,
        )


class AreaSummary(BaseModel):
    """Compact area reference embedded in habit responses."""

    id: int
    name: str
    color: str
    is_archived: bool

    @classmethod
    def from_model(cls, area: Area) -> AreaSummary:
        return cls(
            id=area.id,
            name=area.name,
            color=area.color,
            is_archived=area.is_archived,
        )
