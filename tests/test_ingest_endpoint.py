from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_ingest_telemetry():
    payload = {
        "site_id": "TEST-SITE-001",
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

    response = client.post(
        "/api/v1/telemetry/ingest",
        json=payload,
    )

    assert response.status_code == 201

    data = response.json()

    assert data["site_id"] == "TEST-SITE-001"
    assert data["tower_load_kw"] == 5.0
    assert data["battery_soc"] == 80.0
    assert data["solar_power_kw"] == 3.0
    assert "id" in data