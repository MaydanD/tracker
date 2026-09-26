"""Stage 10 experiment use cases.

Persistence and orchestration only: every rule (lifecycle, windows, comparison)
lives in :mod:`app.domain.experiments`, and every metric comes from the canonical
Stage 7A dataset built once per detail request.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Experiment
from app.db.queries import load_habits
from app.domain.errors import ExperimentNotFoundError, ExperimentStateError
from app.domain.experiments import (
    ExperimentAnalysis,
    analyze,
    effective_end,
    length_of,
    normalise_text,
    normalise_title,
    phase_for,
    status_of,
    validate_window,
    windows_for,
)
from app.domain.owl import ExperimentOwlContext, OwlState, select_experiments
from app.services import analytics


def list_experiments(session: Session) -> list[Experiment]:
    """Newest start first, then newest id: a stable, deterministic order."""
    return list(session.scalars(
        select(Experiment).order_by(Experiment.start_date.desc(), Experiment.id.desc())))


def get_experiment(session: Session, experiment_id: int) -> Experiment:
    experiment = session.get(Experiment, experiment_id)
    if experiment is None:
        raise ExperimentNotFoundError(details={"experiment_id": experiment_id})
    return experiment


def _status(experiment: Experiment, today: date) -> str:
    return status_of(experiment.start_date, experiment.end_date, experiment.cancelled_on, today)


def create_experiment(
    session: Session,
    *,
    title: str,
    hypothesis: str,
    protocol: str,
    start_date: date,
    end_date: date,
) -> Experiment:
    validate_window(start_date, end_date)
    experiment = Experiment(
        title=normalise_title(title),
        hypothesis=normalise_text(hypothesis, field="hypothesis"),
        protocol=normalise_text(protocol, field="protocol"),
        start_date=start_date,
        end_date=end_date,
    )
    session.add(experiment)
    session.commit()
    session.refresh(experiment)
    return experiment


def update_experiment(
    session: Session,
    experiment_id: int,
    *,
    title: str | None = None,
    hypothesis: str | None = None,
    protocol: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    today: date,
) -> Experiment:
    """Edit an experiment under the documented policy.

    * scheduled/active — dates and text may change;
    * completed/cancelled — dates are immutable (history stays comparable), text
      may still be corrected.
    """
    experiment = get_experiment(session, experiment_id)
    status = _status(experiment, today)
    changing_dates = start_date is not None or end_date is not None
    if changing_dates:
        if status in ("completed", "cancelled"):
            raise ExperimentStateError(details={"field": "dates", "status": status})
        validate_window(start_date or experiment.start_date, end_date or experiment.end_date)
        experiment.start_date = start_date or experiment.start_date
        experiment.end_date = end_date or experiment.end_date

    if title is not None:
        experiment.title = normalise_title(title)
    if hypothesis is not None:
        experiment.hypothesis = normalise_text(hypothesis, field="hypothesis")
    if protocol is not None:
        experiment.protocol = normalise_text(protocol, field="protocol")

    session.commit()
    session.refresh(experiment)
    return experiment


def cancel_experiment(session: Session, experiment_id: int, *, today: date) -> Experiment:
    """Stop an experiment early. The cancellation date becomes the effective end."""
    experiment = get_experiment(session, experiment_id)
    status = _status(experiment, today)
    if status in ("completed", "cancelled"):
        raise ExperimentStateError(details={"status": status})
    # The injected clock's date, so the effective window is deterministic.
    experiment.cancelled_on = today
    session.commit()
    session.refresh(experiment)
    return experiment


def build_analysis(session: Session, experiment: Experiment, *, today: date) -> ExperimentAnalysis:
    """One bounded dataset build over before + during + after; nothing loaded twice."""
    windows = windows_for(experiment.start_date, experiment.end_date,
                          cancelled_on=experiment.cancelled_on)
    spans = [w for w in (windows.before, windows.during, windows.after) if length_of(w)]
    if spans:
        start = min(window.start for window in spans)
        end = max(window.end for window in spans)
    else:
        start = end = experiment.start_date
    dataset = analytics.get_dataset(session, start, end, today=today)
    # Presentation labels for the comparison. One metadata query, never per day;
    # the current habit name is what the user recognizes today.
    names = {habit.id: habit.current_version.name
             for habit in load_habits(session, include_archived=True)}
    return analyze(dataset, windows, today=today, habit_names=names)


def find_overlaps(session: Session, experiment: Experiment) -> list[Experiment]:
    """Other experiments whose effective window intersects this one (self excluded)."""
    current_end = effective_end(experiment.start_date, experiment.end_date, experiment.cancelled_on)
    if current_end < experiment.start_date:
        return []
    overlaps = []
    for other in list_experiments(session):
        if other.id == experiment.id:
            continue
        other_end = effective_end(other.start_date, other.end_date, other.cancelled_on)
        if other_end < other.start_date:
            continue
        if other.start_date <= current_end and other_end >= experiment.start_date:
            overlaps.append(other)
    return overlaps


def effective_end_of(experiment: Experiment) -> date:
    return effective_end(experiment.start_date, experiment.end_date, experiment.cancelled_on)


def experiments_owl(session: Session, experiments: list[Experiment], *, today: date) -> OwlState | None:
    """The single experiment banner state; at most one dataset build on the list page."""
    active = next((e for e in experiments if _status(e, today) == "active"), None)
    if active is not None:
        phase = phase_for(active.start_date, active.end_date, active.cancelled_on, today)
        return select_experiments(ExperimentOwlContext(
            active_title=active.title, active_day=phase.day_index, active_total=phase.days_total))
    completed = next((e for e in experiments if _status(e, today) == "completed"), None)
    if completed is None:
        return None
    analysis = build_analysis(session, completed, today=today)
    return select_experiments(ExperimentOwlContext(
        completed_title=completed.title, completed_sufficient=analysis.sufficient))
