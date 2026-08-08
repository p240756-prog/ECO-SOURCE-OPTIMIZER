from datetime import datetime

from app.db.models import Telemetry
from app.statebuilder.decision_context import DecisionContext


class TelemetryAdapter:
    """
    Converts a database Telemetry record into the canonical
    DecisionContext used by the intelligence layer.

    This class performs data translation only.
    It does not make optimization decisions.
    """

    @staticmethod
    def to_decision_context(telemetry: Telemetry) -> DecisionContext:

        timestamp = telemetry.timestamp

        # -------------------------
        # Time
        # -------------------------

        hour_of_day = timestamp.hour

        # -------------------------
        # Solar
        # -------------------------

        solar_kw = telemetry.solar_power_kw or 0.0

        solar_available = solar_kw > 0

        # -------------------------
        # Battery
        # -------------------------

        battery_soc = telemetry.battery_soc or 0.0
        battery_soh = telemetry.battery_health or 0.0

        battery_available = (
            battery_soh > 0
            and battery_soc > 0
        )

        battery_safe_to_discharge = (
            battery_available
            and battery_soc > 20.0
            and battery_soh >= 80.0
        )

        # -------------------------
        # Grid
        # -------------------------

        grid_available = bool(telemetry.grid_available)

        grid_kw = telemetry.grid_power_kw or 0.0
        grid_frequency = telemetry.grid_frequency_hz or 0.0

        # -------------------------
        # Generator
        # -------------------------

        generator_available = bool(
            telemetry.generator_available
        )

        generator_kw = telemetry.generator_power_kw or 0.0

        fuel_level = telemetry.fuel_level or 0.0

        generator_fuel_low_alert = fuel_level <= 20.0

        # -------------------------
        # Tariff
        # -------------------------

        tariff_period = telemetry.tariff_type or "unknown"

        electricity_price = (
            telemetry.electricity_price or 0.0
        )

        # -------------------------
        # Current source
        # -------------------------

        current_source = (
            telemetry.power_source or "unknown"
        )

        # -------------------------
        # Decision Context
        # -------------------------

        return DecisionContext(

            site_id=telemetry.site_id,

            country="PK",

            hour_of_day=hour_of_day,

            tariff_period=tariff_period,

            total_load_kw=telemetry.tower_load_kw,

            solar_available=solar_available,

            solar_capacity_kw=5.0,

            solar_kw=solar_kw,

            battery_available=battery_available,

            battery_capacity_kwh=20.0,

            battery_soc_percent=battery_soc,

            battery_soh_percent=battery_soh,

            battery_safe_to_discharge=(
                battery_safe_to_discharge
            ),

            battery_max_charge_kw=5.0,

            battery_max_discharge_kw=5.0,

            battery_wear_cost_per_kwh=2.0,

            grid_available=grid_available,

            grid_capacity_kw=10.0,

            grid_kw=grid_kw,

            grid_frequency_hz=grid_frequency,

            grid_tariff_per_kwh=electricity_price,

            peak_tariff_per_kwh=0.0,

            off_peak_tariff_per_kwh=0.0,

            generator_available=generator_available,

            generator_capacity_kw=10.0,

            generator_kw=generator_kw,

            generator_fuel_level_percent=fuel_level,

            generator_fuel_low_alert=(
                generator_fuel_low_alert
            ),

            generator_fuel_consumption_liter_hour=(
                telemetry.fuel_consumption_lph or 0.0
            ),

            generator_fuel_cost_per_liter=0.0,

            current_active_source=current_source,
        )