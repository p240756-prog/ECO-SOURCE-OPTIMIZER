from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureSet:
    """
    Derived features used by the intelligence layer.
    """

    solar_load_ratio: float
    grid_load_ratio: float
    power_supply_ratio: float
    battery_reserve_margin: float
    thermal_stress: float


class FeatureExtractor:
    """
    Converts raw telemetry values into normalized intelligence features.

    This class does not make decisions. It only derives features.
    """

    def __init__(
        self,
        battery_reserve_percent: float = 20.0,
        thermal_warning_celsius: float = 40.0,
        thermal_critical_celsius: float = 55.0,
    ) -> None:
        self.battery_reserve_percent = battery_reserve_percent
        self.thermal_warning_celsius = thermal_warning_celsius
        self.thermal_critical_celsius = thermal_critical_celsius

    def extract(
        self,
        *,
        tower_load_kw: float,
        solar_power_kw: float,
        grid_power_kw: float,
        battery_soc_percent: float,
        temperature: float,
    ) -> FeatureSet:
        self._validate(
            tower_load_kw=tower_load_kw,
            solar_power_kw=solar_power_kw,
            grid_power_kw=grid_power_kw,
            battery_soc_percent=battery_soc_percent,
        )

        if tower_load_kw == 0:
            solar_load_ratio = 0.0
            grid_load_ratio = 0.0
            power_supply_ratio = 0.0
        else:
            solar_load_ratio = solar_power_kw / tower_load_kw
            grid_load_ratio = grid_power_kw / tower_load_kw
            power_supply_ratio = (
                solar_power_kw + grid_power_kw
            ) / tower_load_kw

        battery_reserve_margin = (
            battery_soc_percent - self.battery_reserve_percent
        )

        if temperature <= self.thermal_warning_celsius:
            thermal_stress = 0.0
        elif temperature >= self.thermal_critical_celsius:
            thermal_stress = 1.0
        else:
            thermal_stress = (
                temperature - self.thermal_warning_celsius
            ) / (
                self.thermal_critical_celsius
                - self.thermal_warning_celsius
            )

        return FeatureSet(
            solar_load_ratio=solar_load_ratio,
            grid_load_ratio=grid_load_ratio,
            power_supply_ratio=power_supply_ratio,
            battery_reserve_margin=battery_reserve_margin,
            thermal_stress=thermal_stress,
        )

    @staticmethod
    def _validate(
        *,
        tower_load_kw: float,
        solar_power_kw: float,
        grid_power_kw: float,
        battery_soc_percent: float,
    ) -> None:
        if tower_load_kw < 0:
            raise ValueError("tower_load_kw cannot be negative.")

        if solar_power_kw < 0:
            raise ValueError("solar_power_kw cannot be negative.")

        if grid_power_kw < 0:
            raise ValueError("grid_power_kw cannot be negative.")

        if not 0 <= battery_soc_percent <= 100:
            raise ValueError(
                "battery_soc_percent must be between 0 and 100."
            )