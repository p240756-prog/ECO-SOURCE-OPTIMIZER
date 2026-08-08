from fastapi import FastAPI
from app.api.errors import register_exception_handlers
from app.api.routes_health import router as health_router
from app.api.routes_ingest import router as ingest_router
from app.api.routes_state import router as state_router
from app.api.routes_recommendations import (
    router as recommendations_router,
)
from app.api.routes_alerts import router as alerts_router
from app.api.routes_reports import (
    router as reports_router,
)

app = FastAPI(
    title="EcoSourceOptimizer",
    version="1.0.0",
)

register_exception_handlers(app)

app.include_router(
    health_router,
)

app.include_router(
    ingest_router,
)

app.include_router(
    state_router,
)

app.include_router(
    recommendations_router,
)

app.include_router(
    alerts_router,
)

app.include_router(
    reports_router,
)