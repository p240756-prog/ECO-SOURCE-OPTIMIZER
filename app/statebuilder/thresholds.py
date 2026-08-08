class BatteryThresholds:
    """
    Battery operational limits.
    """

    CRITICAL_SOC = 20.0
    LOW_SOC = 40.0
    HIGH_SOC = 80.0

    HEALTH_WARNING = 80.0

    # Battery must retain this reserve for normal operation.
    MIN_DISCHARGE_RESERVE_SOC = 25.0


class GridThresholds:
    """
    Grid quality limits.
    """

    MIN_FREQUENCY_HZ = 49.0
    MAX_FREQUENCY_HZ = 51.0

    # Grid must remain inside this range for normal operation.
    EMERGENCY_MIN_FREQUENCY_HZ = 48.0
    EMERGENCY_MAX_FREQUENCY_HZ = 52.0


class GeneratorThresholds:
    """
    Generator operational limits.
    """

    LOW_FUEL_PERCENT = 20.0
    CRITICAL_FUEL_PERCENT = 10.0


class LoadThresholds:
    """
    Telecom site load classification.
    """

    LOW_LOAD_KW = 6.0
    MEDIUM_LOAD_KW = 15.0


class SolarThresholds:
    """
    Solar contribution classification.
    """

    FULL_LOAD_COVERAGE = 1.0
    PARTIAL_LOAD_COVERAGE = 0.5


class TelemetryThresholds:
    """
    Telemetry freshness and quality limits.
    """

    MAX_DATA_AGE_SECONDS = 60


class SwitchingThresholds:
    """
    Minimum source hold durations.
    """

    BATTERY_MIN_HOLD_SECONDS = 1200
    GENERATOR_MIN_HOLD_SECONDS = 600
    GRID_MIN_HOLD_SECONDS = 300
    SOLAR_MIN_HOLD_SECONDS = 300