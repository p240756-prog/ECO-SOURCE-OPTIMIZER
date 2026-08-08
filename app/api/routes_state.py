from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import StateResponse
from app.db.models import Telemetry
from app.db.sessions import get_db

from app.statebuilder.adapter import TelemetryAdapter
from app.statebuilder.state_builder import StateBuilder


router = APIRouter(
    prefix="/api/v1/state",
    tags=["State"],
)


state_builder = StateBuilder()


@router.get(
    "/{site_id}",
    response_model=StateResponse,
)
def get_latest_state(
    site_id: str,
    db: Session = Depends(get_db),
):
    telemetry = (
        db.query(Telemetry)
        .filter(Telemetry.site_id == site_id)
        .order_by(Telemetry.timestamp.desc())
        .first()
    )

    if telemetry is None:
        raise HTTPException(
            status_code=404,
            detail=f"No telemetry found for site '{site_id}'.",
        )

    context = TelemetryAdapter.to_decision_context(
        telemetry,
    )

    state = state_builder.build(
        context,
    )

    return StateResponse(
        battery_state=state.battery_state,
        solar_state=state.solar_state,
        grid_state=state.grid_state,
        generator_state=state.generator_state,
        overall_state=state.overall_state,
        battery_available=state.battery_available,
        solar_available=state.solar_available,
        grid_available=state.grid_available,
        generator_available=state.generator_available,
        battery_safe=state.battery_safe,
        solar_operational=state.solar_operational,
        grid_stable=state.grid_stable,
        generator_ready=state.generator_ready,
        system_safe=state.system_safe,
    )