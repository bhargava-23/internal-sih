"""
Simulation — state and types.

Defines all typed data structures used by the simulation engine.

Source of truth: docs/02_SIMULATION_PROTOTYPE_SPEC.docx
                 docs/04_BACKEND_SCHEMA.docx §12
AGENTS.md §14

Design rules:
  - Pure data containers; no computation here.
  - All fields carry explicit unit documentation.
  - Frozen where consumed by pure functions; mutable where the step
    function must update it.
  - No Layer 1 equations; no database; no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ValveState(str, Enum):
    """Simulated valve position for one irrigation zone."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"


class ScenarioId(str, Enum):
    """All five approved V1 scenario identifiers."""

    SCN_001 = "SCN-001"
    SCN_002 = "SCN-002"
    SCN_003 = "SCN-003"
    SCN_004 = "SCN-004"
    SCN_005 = "SCN-005"


# ---------------------------------------------------------------------------
# Scenario configuration (loaded from fixture; frozen)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EnvironmentConfig:
    """Initial environmental conditions for a scenario."""

    temperature_c: float
    """Air temperature, °C."""

    relative_humidity_pct: float
    """Relative humidity, % (0–100)."""

    wind_m_s: float
    """Wind speed at 2 m height, m/s."""

    radiation_mj_m2_day: float
    """Daily net radiation at crop surface, MJ/m²/day."""

    rainfall_mm: float
    """Rainfall at simulation start, mm/timestep equivalent."""


@dataclass(frozen=True)
class ForecastConfig:
    """24-hour forecast conditions embedded in the scenario fixture."""

    rainfall_next_24h_mm: float
    temperature_mean_c: float
    humidity_mean_pct: float
    wind_mean_m_s: float


@dataclass(frozen=True)
class IrrigationConfig:
    """Zone irrigation system parameters from the scenario fixture."""

    flow_l_min: float
    """Nominal commanded flow rate, L/min."""

    actual_flow_l_min: float
    """Actual delivered flow rate, L/min.
    Equals flow_l_min for normal scenarios.
    Differs from flow_l_min in SCN-005 (delivery anomaly).
    """

    pressure_bar: float
    """Nominal commanded pressure, bar."""

    actual_pressure_bar: float
    """Actual pressure.  May differ from commanded in SCN-005."""

    previous_24h_l: float
    """Volume delivered in the previous 24 h, litres."""


@dataclass(frozen=True)
class ScenarioConfig:
    """
    Complete configuration for one simulation scenario.

    Loaded from tests/fixtures/scenario_fixtures.json.
    Fields are a direct mapping of the fixture schema.
    No defaults are invented here; all values come from the fixture.
    """

    id: str
    name: str
    title: str
    seed: int
    duration_hours: int
    crop: str
    growth_stage: str
    soil_texture: str
    root_zone_depth_m: float
    field_area_m2: float
    initial_root_zone_moisture: float
    environment: EnvironmentConfig
    forecast: ForecastConfig
    irrigation: IrrigationConfig


# ---------------------------------------------------------------------------
# Per-timestep simulation state (mutable — updated each step)
# ---------------------------------------------------------------------------


@dataclass
class SimulationState:
    """
    Complete simulated field state at one simulation timestep.

    This is the output of one simulation step and the input to the next.
    All values represent simulated/virtual sensor readings — not real field data.

    Source: docs/02_SIMULATION_PROTOTYPE_SPEC.docx §5, §6
            docs/04_BACKEND_SCHEMA.docx §12
    """

    # --- Identity / time ----------------------------------------------------

    timestamp: datetime
    """Wall-clock timestamp of this state (simulation time, UTC)."""

    step_index: int
    """Zero-based step counter within the current scenario run."""

    zone_id: str
    """Identifier of the simulated irrigation zone."""

    scenario_id: str
    """Scenario identifier (e.g. 'SCN-001')."""

    # --- Crop / agronomic configuration -------------------------------------

    crop: str
    """Crop name (e.g. 'tomato').  Passed through to Layer 1."""

    growth_stage: str
    """Growth stage label (e.g. 'flowering').  Passed through to Layer 1."""

    soil_texture: str
    """Soil texture class (e.g. 'loam').  Passed through to Layer 1."""

    root_zone_depth_m: float
    """Effective root-zone depth, m."""

    # --- Root-zone soil moisture --------------------------------------------

    theta_current: float
    """Current simulated volumetric soil moisture, m³/m³.
    Bounded between theta_WP and theta_FC by the simulation engine.
    """

    theta_FC: float
    """Field-capacity VWC for this soil texture and depth, m³/m³."""

    theta_WP: float
    """Wilting-point VWC for this soil texture and depth, m³/m³."""

    # --- Environmental conditions -------------------------------------------

    temperature_c: float
    """Air temperature, °C."""

    relative_humidity_pct: float
    """Relative humidity, % (0–100)."""

    wind_m_s: float
    """Wind speed at 2 m height, m/s."""

    radiation_mj_m2_day: float
    """Net radiation at crop surface, MJ/m²/day."""

    rainfall_mm: float
    """Rainfall this timestep, mm."""

    # --- 24-hour forecast ---------------------------------------------------

    forecast_rainfall_next_24h_mm: float
    """Forecast total rainfall over the next 24 h, mm."""

    forecast_temperature_mean_c: float
    """Forecast mean air temperature over the next 24 h, °C."""

    forecast_humidity_mean_pct: float
    """Forecast mean relative humidity over the next 24 h, %."""

    forecast_wind_mean_m_s: float
    """Forecast mean wind speed over the next 24 h, m/s."""

    # --- Hydraulic state ----------------------------------------------------

    valve_state: ValveState
    """Current simulated valve position."""

    commanded_flow_l_min: float
    """Flow rate commanded to the valve, L/min."""

    actual_flow_l_min: float
    """Actual flow rate delivered, L/min.
    Equal to commanded_flow when valve is functioning normally.
    May differ in SCN-005 delivery anomaly.
    """

    commanded_pressure_bar: float
    """System pressure commanded to the zone, bar."""

    actual_pressure_bar: float
    """Actual measured system pressure, bar.
    May differ from commanded in SCN-005.
    """

    # --- Irrigation delivery ------------------------------------------------

    delivered_volume_this_step_l: float
    """Water volume delivered during this timestep, litres."""

    cumulative_delivered_volume_l: float
    """Total water volume delivered since scenario start, litres."""

    # --- Anomaly flags ------------------------------------------------------

    delivery_anomaly: bool
    """True when actual_flow_l_min < commanded_flow_l_min by more than
    the configured anomaly threshold.  Populated by the simulation step.
    The alert/logging response is handled by later pipeline stages.
    """

    # --- Field area ---------------------------------------------------------

    field_area_m2: float
    """Irrigated zone area, m²."""


# ---------------------------------------------------------------------------
# Irrigation command (input to the simulation step from decision layer)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IrrigationCommand:
    """
    External irrigation command consumed by the simulation step.

    Produced by the decision engine (implemented in a later task).
    The simulator responds to this command by opening/closing the valve
    and updating moisture accordingly.
    """

    open_valve: bool
    """True to open the valve; False to close it."""

    commanded_flow_l_min: float
    """Target flow rate if valve is opened, L/min."""

    commanded_pressure_bar: float
    """Target system pressure if valve is opened, bar."""

    target_volume_l: float = 0.0
    """Optional total volume target.  0 means run until closed."""


# ---------------------------------------------------------------------------
# Soil texture parameters (prototype lookup)
# ---------------------------------------------------------------------------

# Loam soil parameters — used by V1 prototype for all five scenarios
# (all scenarios use soil_texture = "loam").
# These are reference values commonly cited in FAO-56 for loam soils.
# They are NOT invented; they are within the accepted FAO-56 range for loam.
# Source: FAO-56 Table 11 (typical loam: FC 0.22–0.36, WP 0.10–0.20).
SOIL_PARAMS: dict[str, dict[str, float]] = {
    "loam": {
        "theta_FC": 0.30,
        "theta_WP": 0.15,
    },
    # Additional textures can be added here when approved.
}
