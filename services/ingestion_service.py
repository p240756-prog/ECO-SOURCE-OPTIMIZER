from sqlalchemy.orm import Session

from app.api.schemas import TelemetryCreate
from app.db.models import Telemetry


def create_telemetry(
    db: Session,
    telemetry_data: TelemetryCreate,
) -> Telemetry:

    telemetry = Telemetry(
        site_id=telemetry_data.site_id,
        timestamp=telemetry_data.timestamp,

        # Load
        tower_load_kw=telemetry_data.tower_load_kw,
        energy_consumption_kwh=(
            telemetry_data.energy_consumption_kwh
        ),

        # Solar
        solar_power_kw=telemetry_data.solar_power_kw,
        solar_irradiance=telemetry_data.solar_irradiance,

        # Battery
        battery_soc=telemetry_data.battery_soc,
        battery_health=telemetry_data.battery_health,
        battery_status=telemetry_data.battery_status,
        battery_voltage=telemetry_data.battery_voltage,
        battery_current=telemetry_data.battery_current,
        battery_temperature=(
            telemetry_data.battery_temperature
        ),

        # Grid
        grid_available=telemetry_data.grid_available,
        grid_power_kw=telemetry_data.grid_power_kw,
        grid_voltage=telemetry_data.grid_voltage,
        grid_frequency_hz=telemetry_data.grid_frequency_hz,
        electricity_price=telemetry_data.electricity_price,
        tariff_type=telemetry_data.tariff_type,

        # Generator
        generator_available=(
            telemetry_data.generator_available
        ),
        generator_status=telemetry_data.generator_status,
        generator_power_kw=(
            telemetry_data.generator_power_kw
        ),
        fuel_level=telemetry_data.fuel_level,
        fuel_consumption_lph=(
            telemetry_data.fuel_consumption_lph
        ),

        # Environment
        temperature=telemetry_data.temperature,

        # Operation
        power_source=telemetry_data.power_source,
        equipment_status=telemetry_data.equipment_status,
    )

    db.add(telemetry)
    db.commit()
    db.refresh(telemetry)

    return telemetry