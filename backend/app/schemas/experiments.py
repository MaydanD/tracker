"""Typed Stage 10 experiment contracts.

Format-level constraints (lengths, required fields) live here; the product rules
(date order, duration, edit policy, text normalisation) live in
``app.domain.experiments`` so a single place decides what a valid experiment is.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.db.models import Experiment
from app.domain.experiments import (
    TEXT_MAX_LENGTH,
    TITLE_MAX_LENGTH,
    ExperimentAnalysis,
    ExperimentPhase,
    ExperimentStatus,
    phase_for,
    status_of,
)
from app.domain.owl import OwlState


class ExperimentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    hypothesis: str = Field(min_length=1, max_length=TEXT_MAX_LENGTH)
    protocol: str = Field(min_length=1, max_length=TEXT_MAX_LENGTH)
    start_date: date
    end_date: date


class ExperimentUpdate(BaseModel):
    """Partial update: send only the fields that change."""

    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX_LENGTH)
    hypothesis: str | None = Field(default=None, min_length=1, max_length=TEXT_MAX_LENGTH)
    protocol: str | None = Field(default=None, min_length=1, max_length=TEXT_MAX_LENGTH)
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def _require_something_to_change(self) -> ExperimentUpdate:
        if all(value is None for value in (self.title, self.hypothesis, self.protocol,
                                           self.start_date, self.end_date)):
            raise ValueError("Provide at least one field to update.")
        return self


class ExperimentRead(BaseModel):
    id: int
    title: str
    hypothesis: str
    protocol: str
    start_date: date
    end_date: date
    status: ExperimentStatus
    phase: ExperimentPhase
    cancelled_on: date | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, experiment: Experiment, *, today: date) -> ExperimentRead:
        cancelled_on = experiment.cancelled_on
        return cls(
            id=experiment.id,
            title=experiment.title,
            hypothesis=experiment.hypothesis,
            protocol=experiment.protocol,
            start_date=experiment.start_date,
            end_date=experiment.end_date,
            status=status_of(experiment.start_date, experiment.end_date, cancelled_on, today),
            phase=phase_for(experiment.start_date, experiment.end_date, cancelled_on, today),
            cancelled_on=cancelled_on,
            created_at=experiment.created_at,
            updated_at=experiment.updated_at,
        )


class ExperimentOverlapRead(BaseModel):
    id: int
    title: str
    start_date: date
    end_date: date


class ExperimentListRead(BaseModel):
    experiments: list[ExperimentRead]
    # Stage 9 Owl reuse: a single experiment-related banner for the list page.
    owl: OwlState | None = None


class ExperimentDetailRead(BaseModel):
    experiment: ExperimentRead
    overlaps: list[ExperimentOverlapRead]
    # Descriptive before/during/after comparison over the canonical dataset.
    analysis: ExperimentAnalysis
