"""Insight history snapshots.

Stage 7 analytics are read-only and stateless. Stage 8 needs the one thing that
genuinely has to persist: how the evidence for one hypothesis changed over time.
A snapshot stores only the fields needed to read that history back — never a copy
of the analytics dataset.

Identity is ``fingerprint`` (a deterministic hash of the stable variable keys,
grain, lag and insight type). ``x_label``/``y_label`` are presentation metadata
captured at evaluation time, so history stays readable after a habit is renamed
or archived; they are never part of the identity.

``UniqueConstraint(fingerprint, evaluated_on)`` is what makes snapshotting
idempotent: at most one snapshot per hypothesis per calendar day, so refreshing
the page can never grow the history.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.base import Base


class InsightSnapshot(Base):
    """One evaluated state of one insight hypothesis on one calendar day."""

    __tablename__ = "insight_snapshots"
    __table_args__ = (
        UniqueConstraint("fingerprint", "evaluated_on", name="fingerprint_evaluated_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    evaluated_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    # Stable identity of the hypothesis, plus the labels that were current then.
    x_key: Mapped[str] = mapped_column(String(160), nullable=False)
    y_key: Mapped[str] = mapped_column(String(160), nullable=False)
    x_label: Mapped[str] = mapped_column(String(160), nullable=False)
    y_label: Mapped[str] = mapped_column(String(160), nullable=False)
    grain: Mapped[str] = mapped_column(String(16), nullable=False)
    lag: Mapped[int] = mapped_column(Integer, nullable=False)
    lag_unit: Mapped[str | None] = mapped_column(String(8), nullable=True)
    orientation: Mapped[str] = mapped_column(String(16), nullable=False)

    # Evidence summary: enough to read the trend back, no raw observations.
    relationship_method: Mapped[str | None] = mapped_column(String(24), nullable=True)
    coefficient: Mapped[float | None] = mapped_column(Float, nullable=True)
    n: Mapped[int] = mapped_column(Integer, nullable=False)
    pair_coverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(24), nullable=True)
    guardrail_verdict: Mapped[str] = mapped_column(String(24), nullable=False)
    presentation_status: Mapped[str] = mapped_column(String(24), nullable=False)
    blocking_reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    statement: Mapped[str] = mapped_column(Text, nullable=False)

    # Provenance: a history entry stays interpretable after a policy changes.
    insight_policy_version: Mapped[str] = mapped_column(String(16), nullable=False)
    guardrail_policy_version: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence_policy_version: Mapped[str] = mapped_column(String(16), nullable=False)
    template_version: Mapped[str] = mapped_column(String(16), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    # Only changes when the evidence itself changes: an identical same-day
    # refresh leaves the row completely untouched.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        return (f"<InsightSnapshot {self.fingerprint[:12]} on={self.evaluated_on} "
                f"status={self.presentation_status}>")
