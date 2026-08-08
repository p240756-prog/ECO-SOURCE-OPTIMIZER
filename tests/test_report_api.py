from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_decision_report_returns_authoritative_trail():
    site_id = "REPORT-SITE-001"

    payload = {
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

    ingest_response = client.post(
        "/api/v1/telemetry/ingest",
        json=payload,
    )

    assert ingest_response.status_code == 201

    response = client.get(
        f"/api/v1/reports/decision/{site_id}",
    )

    assert response.status_code == 200

    data = response.json()

    assert data["site_id"] == site_id

    assert "selected_source" in data
    assert "estimated_cost_per_kwh" in data
    assert "emergency_mode" in data
    assert "reason" in data

    assert "state" in data
    assert "feasibility" in data
    assert "safety" in data
    assert "costs" in data
    assert "optimization" in data

    assert "power_anomaly" in data
    assert "fuel_anomaly" in data

    assert "alert_count" in data

    assert "overall_state" in data["state"]

    assert "solar" in data["feasibility"]
    assert "battery" in data["feasibility"]
    assert "grid" in data["feasibility"]
    assert "generator" in data["feasibility"]

    assert "solar" in data["costs"]
    assert "battery" in data["costs"]
    assert "grid" in data["costs"]
    assert "generator" in data["costs"]

    assert isinstance(
        data["optimization"]["candidates"],
        list,
    )


def test_decision_report_returns_404_for_unknown_site():
    response = client.get(
        "/api/v1/reports/decision/DOES-NOT-EXIST",
    )

    assert response.status_code == 404