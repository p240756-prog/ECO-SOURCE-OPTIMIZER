from dataclasses import dataclass


@dataclass
class DecisionContext:
    """
    Complete telemetry context for Eco Source Optimizer.

    This is the single source of truth for all
    optimization and decision modules.
    """

    # Site metadata
    site_id: str
    country: str

    # Time / tariff
    hour_of_day: int
    tariff_period: str


    # Load
    total_load_kw: float


    # Solar
    solar_available: bool
    solar_capacity_kw: float
    solar_kw: float


    # Battery
    battery_available: bool
    battery_capacity_kwh: float
    battery_soc_percent: float
    battery_soh_percent: float
    battery_safe_to_discharge: bool

    battery_max_charge_kw: float
    battery_max_discharge_kw: float

    battery_wear_cost_per_kwh: float | None


    # Grid
    grid_available: bool
    grid_capacity_kw: float
    grid_kw: float

    grid_frequency_hz: float

    grid_tariff_per_kwh: float
    peak_tariff_per_kwh: float
    off_peak_tariff_per_kwh: float


    # Generator
    generator_available: bool
    generator_capacity_kw: float
    generator_kw: float

    generator_fuel_level_percent: float
    generator_fuel_low_alert: bool

    generator_fuel_consumption_liter_hour: float
    generator_fuel_cost_per_liter: float | None


    # Current operation
    current_active_source: str