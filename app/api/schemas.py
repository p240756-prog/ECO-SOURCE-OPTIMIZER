from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# TELEMETRY
# ============================================================


class TelemetryCreate(BaseModel):
    site_id: str = Field(..., min_length=1, max_length=100)
    timestamp: datetime

    # Load
    tower_load_kw: float = Field(..., ge=0)
    energy_consumption_kwh: float | None = Field(default=None, ge=0)

    # Solar
    solar_power_kw: float | None = Field(default=None, ge=0)
    solar_irradiance: float | None = Field(default=None, ge=0)

    # Battery
    battery_soc: float | None = Field(default=None, ge=0, le=100)
    battery_health: float | None = Field(default=None, ge=0, le=100)
    battery_status: str | None = None
    battery_voltage: float | None = Field(default=None, ge=0)
    battery_current: float | None = None
    battery_temperature: float | None = None

    # Grid
    grid_available: bool | None = None
    grid_power_kw: float | None = Field(default=None, ge=0)
    grid_voltage: float | None = Field(default=None, ge=0)
    grid_frequency_hz: float | None = Field(default=None, ge=0)
    electricity_price: float | None = Field(default=None, ge=0)
    tariff_type: str | None = None

    # Generator
    generator_available: bool | None = None
    generator_status: str | None = None
    generator_power_kw: float | None = Field(default=None, ge=0)
    fuel_level: float | None = Field(default=None, ge=0, le=100)
    fuel_consumption_lph: float | None = Field(default=None, ge=0)

    # Environment
    temperature: float | None = None

    # Current operation
    power_source: str | None = None
    equipment_status: str | None = None


class TelemetryResponse(TelemetryCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# STATE
# ============================================================


class StateResponse(BaseModel):
    battery_state: str
    solar_state: str
    grid_state: str
    generator_state: str
    overall_state: str

    battery_available: bool
    solar_available: bool
    grid_available: bool
    generator_available: bool

    battery_safe: bool
    solar_operational: bool
    grid_stable: bool
    generator_ready: bool

    system_safe: bool


# ============================================================
# SOURCE FEASIBILITY
# ============================================================


class SourceFeasibilityResponse(BaseModel):
    solar: bool
    battery: bool
    grid: bool
    generator: bool

    solar_reason: str
    battery_reason: str
    grid_reason: str
    generator_reason: str


# ============================================================
# SAFETY
# ============================================================


class SafetyResponse(BaseModel):
    solar_allowed: bool
    battery_allowed: bool
    grid_allowed: bool
    generator_allowed: bool

    solar_reason: str
    battery_reason: str
    grid_reason: str
    generator_reason: str

    emergency_mode: bool


# ============================================================
# COST
# ============================================================


class SourceCostResponse(BaseModel):
    source: str

    cost_per_kwh: float | None

    available: bool
    economically_valid: bool

    reason: str


class CostComparisonResponse(BaseModel):
    solar: SourceCostResponse
    battery: SourceCostResponse
    grid: SourceCostResponse
    generator: SourceCostResponse


# ============================================================
# OPTIMIZATION
# ============================================================


class OptimizationCandidateResponse(BaseModel):
    source: str

    cost_per_kwh: float | None

    eligible: bool

    reason: str


class OptimizationResponse(BaseModel):
    selected_source: str | None

    estimated_cost_per_kwh: float | None

    emergency_mode: bool

    reason: str

    candidates: list[OptimizationCandidateResponse]


# ============================================================
# ANOMALIES
# ============================================================


class PowerAnomalyResponse(BaseModel):
    detected: bool
    severity: str
    reasons: list[str]


class FuelAnomalyResponse(BaseModel):
    detected: bool
    severity: str
    reasons: list[str]


# ============================================================
# FINAL RECOMMENDATION
# ============================================================


class RecommendationResponse(BaseModel):
    site_id: str
    timestamp: datetime

    selected_source: str | None

    estimated_cost_per_kwh: float | None

    emergency_mode: bool

    reason: str

    state: StateResponse

    feasibility: SourceFeasibilityResponse

    safety: SafetyResponse

    costs: CostComparisonResponse

    optimization: OptimizationResponse

    power_anomaly: PowerAnomalyResponse

    fuel_anomaly: FuelAnomalyResponse


# ============================================================
# HEALTH
# ============================================================


class HealthResponse(BaseModel):
    status: str


# ============================================================
# ALERTS
# ============================================================


class AlertResponse(BaseModel):
    id: int | None = None

    site_id: str

    alert_type: str

    severity: str

    message: str

    timestamp: datetime | None = None

# ============================================================
# DECISION REPORT
# ============================================================


class DecisionReportResponse(BaseModel):
    """
    Dashboard/reporting representation of the authoritative
    decision pipeline.

    This endpoint exposes the complete decision trail without
    changing or recalculating any decision logic.
    """

    site_id: str
    timestamp: datetime

    selected_source: str | None
    estimated_cost_per_kwh: float | None

    emergency_mode: bool

    reason: str

    state: StateResponse

    feasibility: SourceFeasibilityResponse

    safety: SafetyResponse

    costs: CostComparisonResponse

    optimization: OptimizationResponse

    power_anomaly: PowerAnomalyResponse

    fuel_anomaly: FuelAnomalyResponse

    alert_count: int