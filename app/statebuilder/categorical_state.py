from dataclasses import dataclass


@dataclass
class CategoricalState:
    """
    High-level operational state of the energy system.

    Contains interpreted state only.
    Business decisions belong to the Rule Engine.
    """

    battery_state: str
    solar_state: str
    grid_state: str

    generator_state: str = "UNAVAILABLE"
    overall_state: str = "NORMAL"

    # --------------------------------------------------
    # Availability
    # --------------------------------------------------

    @property
    def battery_available(self) -> bool:
        return self.battery_state not in (
            "CRITICAL",
            "UNAVAILABLE",
        )

    @property
    def solar_available(self) -> bool:
        """
    Solar energy is currently usable.
    """
        return self.solar_state in (
        "AVAILABLE",
        "FULL",
        "PARTIAL",
    )

    @property
    def grid_available(self) -> bool:
        return self.grid_state != "FAILED"

    @property
    def generator_available(self) -> bool:
        return self.generator_state not in (
            "UNAVAILABLE",
            "CRITICAL_FUEL",
        )

    # --------------------------------------------------
    # Safety / Stability
    # --------------------------------------------------

    @property
    def battery_safe(self) -> bool:
        return self.battery_state in (
            "NORMAL",
            "HIGH",
        )

    @property
    def solar_operational(self) -> bool:
        return self.solar_state in (
            "PARTIAL",
            "FULL",
        )

    @property
    def grid_stable(self) -> bool:
        return self.grid_state == "STABLE"

    @property
    def generator_ready(self) -> bool:
        return self.generator_state == "AVAILABLE"

    # --------------------------------------------------
    # Overall
    # --------------------------------------------------

    @property
    def system_safe(self) -> bool:
        return self.overall_state not in (
            "BATTERY_RISK",
            "POWER_RISK",
        )

    def is_safe(self) -> bool:
        return self.system_safe