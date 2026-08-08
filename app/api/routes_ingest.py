from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import TelemetryCreate, TelemetryResponse
from app.db.sessions import get_db
from services.ingestion_service import create_telemetry


router = APIRouter(
    prefix="/api/v1/telemetry",
    tags=["Telemetry"],
)


@router.post(
    "/ingest",
    response_model=TelemetryResponse,
    status_code=201,
)
def ingest_telemetry(
    telemetry: TelemetryCreate,
    db: Session = Depends(get_db),
):
    try:
        return create_telemetry(db, telemetry)

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to ingest telemetry: {str(exc)}",
        )