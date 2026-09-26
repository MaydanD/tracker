"""Stage 10 experiment endpoints.

Thin handlers: they resolve the injected clock, call the service and project the
result. No comparison math lives here.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies import ClockDep, DbSession
from app.schemas.experiments import (
    ExperimentCreate,
    ExperimentDetailRead,
    ExperimentListRead,
    ExperimentOverlapRead,
    ExperimentRead,
    ExperimentUpdate,
)
from app.services import experiments as service

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.get("", response_model=ExperimentListRead, summary="List experiments")
def list_experiments(session: DbSession, clock: ClockDep) -> ExperimentListRead:
    today = clock.today()
    experiments = service.list_experiments(session)
    return ExperimentListRead(
        experiments=[ExperimentRead.from_model(item, today=today) for item in experiments],
        owl=service.experiments_owl(session, experiments, today=today),
    )


@router.post("", response_model=ExperimentRead, status_code=201, summary="Create an experiment")
def create_experiment(payload: ExperimentCreate, session: DbSession, clock: ClockDep) -> ExperimentRead:
    experiment = service.create_experiment(
        session,
        title=payload.title,
        hypothesis=payload.hypothesis,
        protocol=payload.protocol,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    return ExperimentRead.from_model(experiment, today=clock.today())


@router.get("/{experiment_id}", response_model=ExperimentDetailRead, summary="Experiment detail")
def get_experiment(experiment_id: int, session: DbSession, clock: ClockDep) -> ExperimentDetailRead:
    today = clock.today()
    experiment = service.get_experiment(session, experiment_id)
    overlaps = service.find_overlaps(session, experiment)
    analysis = service.build_analysis(session, experiment, today=today)
    return ExperimentDetailRead(
        experiment=ExperimentRead.from_model(experiment, today=today),
        overlaps=[
            ExperimentOverlapRead(
                id=item.id, title=item.title, start_date=item.start_date,
                end_date=service.effective_end_of(item),
            )
            for item in overlaps
        ],
        analysis=analysis,
    )


@router.patch("/{experiment_id}", response_model=ExperimentRead, summary="Update an experiment")
def update_experiment(
    experiment_id: int, payload: ExperimentUpdate, session: DbSession, clock: ClockDep,
) -> ExperimentRead:
    experiment = service.update_experiment(
        session, experiment_id,
        title=payload.title, hypothesis=payload.hypothesis, protocol=payload.protocol,
        start_date=payload.start_date, end_date=payload.end_date, today=clock.today(),
    )
    return ExperimentRead.from_model(experiment, today=clock.today())


@router.post("/{experiment_id}/cancel", response_model=ExperimentRead, summary="Cancel an experiment")
def cancel_experiment(experiment_id: int, session: DbSession, clock: ClockDep) -> ExperimentRead:
    experiment = service.cancel_experiment(session, experiment_id, today=clock.today())
    return ExperimentRead.from_model(experiment, today=clock.today())
