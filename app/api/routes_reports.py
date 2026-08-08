from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import DecisionReportResponse
from app.db.sessions import get_db
from services.recommendation_service import RecommendationService


router = APIRouter(
    prefix="/api/v1/reports",
    tags=["Reports"],
)


recommendation_service = RecommendationService()


@router.get(
    "/decision/{site_id}",
    response_model=DecisionReportResponse,
)
def get_decision_report(
    site_id: str,
    db: Session = Depends(get_db),
):
    """
    Return the authoritative decision report for the
    latest telemetry record of a site.
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
            detail=f"Failed to generate decision report: {str(exc)}",
        )

    decision = result.decision

    return DecisionReportResponse(
        site_id=result.site_id,
        timestamp=result.timestamp,
        selected_source=result.selected_source,
        estimated_cost_per_kwh=result.estimated_cost_per_kwh,
        emergency_mode=result.emergency_mode,
        reason=result.reason,
        state=decision.state,
        feasibility=decision.feasibility,
        safety=decision.safety,
        costs=decision.costs,
        optimization=decision.optimization,
        power_anomaly=result.power_anomaly,
        fuel_anomaly=result.fuel_anomaly,
        alert_count=len(result.alerts),
    )