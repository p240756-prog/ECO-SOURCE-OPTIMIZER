from fastapi import APIRouter

from app.events.event_store import EventStore


router = APIRouter(
    prefix="/api/v1/alerts",
    tags=["Alerts"],
)


event_store = EventStore()


@router.get("")
def get_alerts():
    """
    Return all currently stored alert events.
    """

    return {
        "count": len(event_store.get_all()),
        "alerts": event_store.get_all(),
    }


@router.get("/{site_id}")
def get_site_alerts(
    site_id: str,
):
    """
    Return alert events for a specific site.
    """

    alerts = event_store.get_by_site(site_id)

    return {
        "site_id": site_id,
        "count": len(alerts),
        "alerts": alerts,
    }