
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _telemetry_payload(site_id: str) -> dict:
    return {
        "site_id": site_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tower_load_kw": 5.0,
        "energy_consumption_kwh": 5.0,

        "solar_power_kw": 3.0,
        "solar_irradiance": 700.0,

        "battery_soc": 80.0,
        "battery_health": 95.0,
        "battery_status": "healthy",
        "battery_voltage": 48.0,
        "battery_current": 10.0,
        "battery_temperature": 25.0,

        "grid_available": True,
        "grid_power_kw": 2.0,
        "grid_voltage": 230.0,
        "grid_frequency_hz": 50.0,
        "electricity_price": 20.0,
        "tariff_type": "off_peak",

        "generator_available": True,
        "generator_status": "standby",
        "generator_power_kw": 10.0,
        "fuel_level": 80.0,
        "fuel_consumption_lph": 1.5,

        "temperature": 25.0,

        "power_source": "solar",
        "equipment_status": "normal",
    }


def test_state_api_returns_latest_state():
    site_id = "API-STATE-TEST"

    ingest_response = client.post(
        "/api/v1/telemetry/ingest",
        json=_telemetry_payload(site_id),
    )

    assert ingest_response.status_code == 201

    response = client.get(
        f"/api/v1/state/{site_id}",
    )

    assert response.status_code == 200

    data = response.json()

    assert data["battery_state"]
    assert data["solar_state"]
    assert data["grid_state"]
    assert data["generator_state"]
    assert data["overall_state"]

    assert isinstance(data["battery_available"], bool)
    assert isinstance(data["solar_available"], bool)
    assert isinstance(data["grid_available"], bool)
    assert isinstance(data["generator_available"], bool)

    assert isinstance(data["system_safe"], bool)


def test_recommendation_api_returns_authoritative_decision_trail():
    site_id = "API-RECOMMENDATION-TEST"

    ingest_response = client.post(
        "/api/v1/telemetry/ingest",
        json=_telemetry_payload(site_id),
    )

    assert ingest_response.status_code == 201

    response = client.get(
        f"/api/v1/recommendations/{site_id}",
    )

    assert response.status_code == 200

    data = response.json()

    # ----------------------------------------------------------
    # Final decision
    # ----------------------------------------------------------

    assert data["site_id"] == site_id
    assert "timestamp" in data
    assert "selected_source" in data
    assert "estimated_cost_per_kwh" in data
    assert isinstance(data["emergency_mode"], bool)
    assert data["reason"]

    # ----------------------------------------------------------
    # Complete authoritative decision trail
    # ----------------------------------------------------------

    assert "state" in data
    assert "feasibility" in data
    assert "safety" in data
    assert "costs" in data
    assert "optimization" in data

    # ----------------------------------------------------------
    # State
    # ----------------------------------------------------------

    state = data["state"]

    assert "overall_state" in state
    assert "battery_state" in state
    assert "solar_state" in state
    assert "grid_state" in state
    assert "generator_state" in state
    assert "system_safe" in state

    # ----------------------------------------------------------
    # Feasibility
    # ----------------------------------------------------------

    feasibility = data["feasibility"]

    for source in (
        "solar",
        "battery",
        "grid",
        "generator",
    ):
        assert source in feasibility
        assert f"{source}_reason" in feasibility

    # ----------------------------------------------------------
    # Safety
    # ----------------------------------------------------------

    safety = data["safety"]

    for source in (
        "solar",
        "battery",
        "grid",
        "generator",
    ):
        assert f"{source}_allowed" in safety
        assert f"{source}_reason" in safety

    assert isinstance(
        safety["emergency_mode"],
        bool,
    )

    # ----------------------------------------------------------
    # Economics
    # ----------------------------------------------------------

    costs = data["costs"]

    for source in (
        "solar",
        "battery",
        "grid",
        "generator",
    ):
        source_cost = costs[source]

        assert source_cost["source"] == source
        assert "cost_per_kwh" in source_cost
        assert "available" in source_cost
        assert "economically_valid" in source_cost
        assert "reason" in source_cost

    # ----------------------------------------------------------
    # Optimization
    # ----------------------------------------------------------

    optimization = data["optimization"]

    assert "selected_source" in optimization
    assert "estimated_cost_per_kwh" in optimization
    assert "emergency_mode" in optimization
    assert optimization["reason"]
    assert isinstance(
        optimization["candidates"],
        list,
    )


def test_recommendation_api_returns_404_for_unknown_site():
    response = client.get(
        "/api/v1/recommendations/SITE-DOES-NOT-EXIST",
    )

    assert response.status_code == 404


def test_state_api_returns_404_for_unknown_site():
    response = client.get(
        "/api/v1/state/SITE-DOES-NOT-EXIST",
    )

    assert response.status_code == 404

