from dataclasses import dataclass

from app.statebuilder.categorical_state import CategoricalState
from app.statebuilder.decision_context import DecisionContext


@dataclass
class SourceFeasibility:
    """
    Technical feasibility of each energy source.

    Feasibility answers:
        Can this source physically contribute power?

    Feasibility does NOT decide:
        - safety authorization
        - economic preference
        - source selection
    """

    solar: bool
    battery: bool
    grid: bool
    generator: bool

    solar_reason: str
    battery_reason: str
    grid_reason: str
    generator_reason: str

    @property
    def any_source_available(self) -> bool:
        return (
            self.solar
            or self.battery
            or self.grid
            or self.generator
        )


class SourceFeasibilityEngine:
    """
    Evaluates physical/technical source capability only.
    """

    def evaluate(
        self,
        context: DecisionContext,
        state: CategoricalState,
    ) -> SourceFeasibility:

        load = context.total_load_kw

        # ----------------------------------------------------------
        # SOLAR
        # ----------------------------------------------------------

        if not context.solar_available:
            solar = False
            solar_reason = "Solar system is unavailable."

        elif context.solar_kw <= 0:
            solar = False
            solar_reason = (
                "Solar is available but currently producing no usable power."
            )

        else:
            solar = True

            if context.solar_kw >= load:
                solar_reason = (
                    f"Solar can fully cover the {load:.3f} kW site load "
                    f"with {context.solar_kw:.3f} kW available."
                )
            else:
                solar_reason = (
                    f"Solar can contribute {context.solar_kw:.3f} kW "
                    f"toward the {load:.3f} kW site load."
                )

        # ----------------------------------------------------------
        # BATTERY
        # ----------------------------------------------------------

        if not context.battery_available:
            battery = False
            battery_reason = "Battery is unavailable."

        elif not state.battery_available:
            battery = False
            battery_reason = (
                f"Battery state is {state.battery_state}; "
                "battery is not technically available."
            )

        elif context.battery_soc_percent <= 0:
            battery = False
            battery_reason = "Battery SOC is depleted."

        elif context.battery_max_discharge_kw <= 0:
            battery = False
            battery_reason = (
                "Battery has no positive discharge capability."
            )

        else:
            battery = True
            battery_reason = (
                f"Battery can technically contribute up to "
                f"{context.battery_max_discharge_kw:.3f} kW "
                f"at {context.battery_soc_percent:.1f}% SOC. "
                "Safety and reserve policy are evaluated separately."
            )

        # ----------------------------------------------------------
        # GRID
        # ----------------------------------------------------------

        if not context.grid_available:
            grid = False
            grid_reason = "Grid is unavailable."

        elif not state.grid_stable:
            grid = False
            grid_reason = (
                f"Grid is not stable "
                f"(frequency: {context.grid_frequency_hz:.2f} Hz)."
            )

        elif context.grid_capacity_kw <= 0:
            grid = False
            grid_reason = "Grid capacity is missing or non-positive."

        else:
            grid = True

            if context.grid_capacity_kw < load:
                grid_reason = (
                    f"Grid can technically provide "
                    f"{context.grid_capacity_kw:.3f} kW, "
                    f"below the {load:.3f} kW site load; "
                    "partial contribution is possible."
                )
            else:
                grid_reason = (
                    f"Grid can provide the required load with "
                    f"{context.grid_capacity_kw:.3f} kW capacity."
                )

        # ----------------------------------------------------------
        # GENERATOR
        # ----------------------------------------------------------

        if not context.generator_available:
            generator = False
            generator_reason = "Generator is unavailable."

        elif not state.generator_ready:
            generator = False
            generator_reason = (
                f"Generator state is {state.generator_state}; "
                "normal operation is not permitted."
            )

        elif context.generator_fuel_level_percent <= 0:
            generator = False
            generator_reason = "Generator fuel is depleted."

        elif context.generator_capacity_kw <= 0:
            generator = False
            generator_reason = (
                "Generator capacity is missing or non-positive."
            )

        else:
            generator = True

            if context.generator_capacity_kw < load:
                generator_reason = (
                    f"Generator can technically provide "
                    f"{context.generator_capacity_kw:.3f} kW, "
                    f"below the {load:.3f} kW site load; "
                    "partial contribution is possible."
                )
            else:
                generator_reason = (
                    f"Generator can provide the required load "
                    f"with {context.generator_fuel_level_percent:.1f}% fuel."
                )

        return SourceFeasibility(
            solar=solar,
            battery=battery,
            grid=grid,
            generator=generator,
            solar_reason=solar_reason,
            battery_reason=battery_reason,
            grid_reason=grid_reason,
            generator_reason=generator_reason,
        )