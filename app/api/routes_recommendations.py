from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import (
    RecommendationResponse,
    StateResponse,
    SourceFeasibilityResponse,
    SafetyResponse,
    SourceCostResponse,
    CostComparisonResponse,
    OptimizationCandidateResponse,
    OptimizationResponse,
    PowerAnomalyResponse,
    FuelAnomalyResponse,
)

from app.db.sessions import get_db
from services.recommendation_service import RecommendationService


router = APIRouter(
    prefix="/api/v1/recommendations",
    tags=["Recommendations"],
)


recommendation_service = RecommendationService()


@router.get(
    "/{site_id}",
    response_model=RecommendationResponse,
)
def get_recommendation(
    site_id: str,
    db: Session = Depends(get_db),
):
    """
    Generate the latest energy-source recommendation
    for a site.
    """

    try:
        result = recommendation_service.recommend_latest(
            db=db,
            site_id=site_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate recommendation: {str(exc)}",
        )

    decision = result.decision

    state = decision.state

    state_response = StateResponse(
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

    feasibility = decision.feasibility

    feasibility_response = SourceFeasibilityResponse(
        solar=feasibility.solar,
        battery=feasibility.battery,
        grid=feasibility.grid,
        generator=feasibility.generator,
        solar_reason=feasibility.solar_reason,
        battery_reason=feasibility.battery_reason,
        grid_reason=feasibility.grid_reason,
        generator_reason=feasibility.generator_reason,
    )

    safety = decision.safety

    safety_response = SafetyResponse(
        solar_allowed=safety.solar_allowed,
        battery_allowed=safety.battery_allowed,
        grid_allowed=safety.grid_allowed,
        generator_allowed=safety.generator_allowed,
        solar_reason=safety.solar_reason,
        battery_reason=safety.battery_reason,
        grid_reason=safety.grid_reason,
        generator_reason=safety.generator_reason,
        emergency_mode=safety.emergency_mode,
    )

    costs = decision.costs

    costs_response = CostComparisonResponse(
        solar=SourceCostResponse(
            source=costs.solar.source,
            cost_per_kwh=costs.solar.cost_per_kwh,
            available=costs.solar.available,
            economically_valid=costs.solar.economically_valid,
            reason=costs.solar.reason,
        ),
        battery=SourceCostResponse(
            source=costs.battery.source,
            cost_per_kwh=costs.battery.cost_per_kwh,
            available=costs.battery.available,
            economically_valid=costs.battery.economically_valid,
            reason=costs.battery.reason,
        ),
        grid=SourceCostResponse(
            source=costs.grid.source,
            cost_per_kwh=costs.grid.cost_per_kwh,
            available=costs.grid.available,
            economically_valid=costs.grid.economically_valid,
            reason=costs.grid.reason,
        ),
        generator=SourceCostResponse(
            source=costs.generator.source,
            cost_per_kwh=costs.generator.cost_per_kwh,
            available=costs.generator.available,
            economically_valid=costs.generator.economically_valid,
            reason=costs.generator.reason,
        ),
    )

    optimization = decision.optimization

    optimization_response = OptimizationResponse(
        selected_source=optimization.selected_source,
        estimated_cost_per_kwh=optimization.estimated_cost_per_kwh,
        emergency_mode=optimization.emergency_mode,
        reason=optimization.reason,
        candidates=[
            OptimizationCandidateResponse(
                source=candidate.source,
                cost_per_kwh=candidate.cost_per_kwh,
                eligible=candidate.eligible,
                reason=candidate.reason,
            )
            for candidate in optimization.candidates
        ],
    )

    return RecommendationResponse(
        site_id=result.site_id,
        timestamp=result.timestamp,
        selected_source=result.selected_source,
        estimated_cost_per_kwh=result.estimated_cost_per_kwh,
        emergency_mode=result.emergency_mode,
        reason=result.reason,
        state=state_response,
        feasibility=feasibility_response,
        safety=safety_response,
        costs=costs_response,
        optimization=optimization_response,
        power_anomaly=PowerAnomalyResponse(
            detected=result.power_anomaly.detected,
            severity=result.power_anomaly.severity,
            reasons=result.power_anomaly.reasons,
        ),
        fuel_anomaly=FuelAnomalyResponse(
            detected=result.fuel_anomaly.detected,
            severity=result.fuel_anomaly.severity,
            reasons=result.fuel_anomaly.reasons,
        ),
    )