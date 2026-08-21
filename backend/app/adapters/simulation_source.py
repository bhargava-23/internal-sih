"""
Simulation → telemetry adapter  (T2-03).

Converts a SimulationState into a canonical TelemetryPoint.

This is a PURE CONVERSION ADAPTER ONLY.  It:
  - reads fields from SimulationState;
  - maps them to the canonical TelemetryPoint contract
    (docs/04_BACKEND_SCHEMA.docx §17 — Canonical API Contracts);
  - stamps source = TelemetrySource.SIMULATION on every record.

It does NOT:
  - compute ET0, Kc, ETc, TAW, RAW, depletion, or any agronomic equation;
  - implement simulation stepping logic;
  - write to a database;
  - emit WebSocket or HTTP events;
  - interpret or transform anomaly flags into alerts.

Source of truth:
  docs/04_BACKEND_SCHEMA.docx §17  — TelemetryPoint contract
  docs/04_BACKEND_SCHEMA.docx §18  — telemetry table (sensor values, quality, source)
  docs/02_SIMULATION_PROTOTYPE_SPEC.docx §5 — prototype principle (source labelling)
  AGENTS.md §14  — Simulation Rules (source=simulation, no agronomic duplication)
  AGENTS.md §21  — Data Quality Rules

Canonical TelemetryPoint field => SimulationState mapping
----------------------------------------------------------
timestamp               <- state.timestamp           (preserved as-is)
zone_id                 <- state.zone_id              (preserved as-is)
soil_moisture_rz        <- state.theta_current        [m3/m3]
temperature_c           <- state.temperature_c        [deg C]
humidity_pct            <- state.relative_humidity_pct [%]
wind_mps                <- state.wind_m_s             [m/s]
radiation_mj_m2_day     <- state.radiation_mj_m2_day  [MJ/m2/day]  (nullable)
rainfall_mm             <- state.rainfall_mm          [mm]
flow_lpm                <- state.actual_flow_l_min    [L/min]
pressure_bar            <- state.actual_pressure_bar  [bar]
source                  <- TelemetrySource.SIMULATION  (constant)
quality                 <- TelemetryQuality.VALID      (simulation always valid)

SCN-005 anomaly notes
---------------------
The canonical telemetry record carries actual (delivered) flow and pressure values.
Downstream layers (decision engine, feedback logger) can compare commanded vs actual
by inspecting both the telemetry record and the simulation state.
This adapter does not interpret the anomaly; it exposes the raw values.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.domain.simulation.state import SimulationState


# ---------------------------------------------------------------------------
# Canonical enumerations
# (mirroring docs/04_BACKEND_SCHEMA.docx §17 — source and quality literals)
# ---------------------------------------------------------------------------


class TelemetrySource(str, Enum):
    """Provenance / source marker required by the canonical contract.

    Every record emitted from this adapter uses SIMULATION.
    The HARDWARE value is reserved for the future physical-sensor adapter.
    """

    SIMULATION = "simulation"
    HARDWARE = "hardware"


class TelemetryQuality(str, Enum):
    """Data-quality flag required by the canonical contract.

    The simulation always produces VALID values.
    FLAGGED / INVALID are available for future QC layers (AGENTS.md §21).
    """

    VALID = "valid"
    FLAGGED = "flagged"
    INVALID = "invalid"


# ---------------------------------------------------------------------------
# Canonical TelemetryPoint
# (mirrors docs/04_BACKEND_SCHEMA.docx §17)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TelemetryPoint:
    """
    Canonical single-timestep telemetry record.

    Field names and types match docs/04_BACKEND_SCHEMA.docx §17 exactly.
    The frozen dataclass ensures the record is immutable once created.

    Units
    -----
    timestamp               — ISO-8601 UTC datetime (Python datetime object)
    zone_id                 — string identifier
    soil_moisture_rz        — m3/m3  (volumetric water content, root-zone)
    temperature_c           — deg C
    humidity_pct            — %  (0-100)
    wind_mps                — m/s
    radiation_mj_m2_day     — MJ/m2/day  (None if unavailable)
    rainfall_mm             — mm
    flow_lpm                — L/min
    pressure_bar            — bar
    source                  — TelemetrySource enum
    quality                 — TelemetryQuality enum
    """

    timestamp: datetime
    zone_id: str
    soil_moisture_rz: float       # m3/m3
    temperature_c: float          # deg C
    humidity_pct: float           # %
    wind_mps: float               # m/s
    radiation_mj_m2_day: float | None  # MJ/m2/day — nullable per contract
    rainfall_mm: float            # mm
    flow_lpm: float               # L/min
    pressure_bar: float           # bar
    source: TelemetrySource
    quality: TelemetryQuality


# ---------------------------------------------------------------------------
# Adapter function
# ---------------------------------------------------------------------------


def simulation_state_to_telemetry(state: SimulationState) -> TelemetryPoint:
    """
    Convert a SimulationState to a canonical TelemetryPoint.

    Pure function:
      - deterministic for the same input;
      - does not mutate `state`;
      - performs no agronomic calculation;
      - always stamps source = TelemetrySource.SIMULATION.

    Field mapping (explicit, unit-annotated)
    ----------------------------------------
    state.timestamp               -> timestamp         (UTC datetime, preserved)
    state.zone_id                 -> zone_id           (string, preserved)
    state.theta_current           -> soil_moisture_rz  [m3/m3]
    state.temperature_c           -> temperature_c     [deg C]
    state.relative_humidity_pct   -> humidity_pct      [%]
    state.wind_m_s                -> wind_mps          [m/s]
    state.radiation_mj_m2_day     -> radiation_mj_m2_day [MJ/m2/day]
    state.rainfall_mm             -> rainfall_mm       [mm]
    state.actual_flow_l_min       -> flow_lpm          [L/min]   -- ACTUAL flow
    state.actual_pressure_bar     -> pressure_bar      [bar]     -- ACTUAL pressure
    (constant)                    -> source            = TelemetrySource.SIMULATION
    (constant)                    -> quality           = TelemetryQuality.VALID

    SCN-005 anomaly: uses ACTUAL (delivered) flow and pressure so that the
    commanded-vs-actual distinction is visible to downstream layers.

    Args:
        state: The SimulationState for the current simulation timestep.

    Returns:
        An immutable TelemetryPoint with source=simulation and quality=valid.
    """
    return TelemetryPoint(
        # --- Identity / time ------------------------------------------------
        timestamp=state.timestamp,                  # UTC datetime — preserved as-is
        zone_id=state.zone_id,                      # string — preserved as-is

        # --- Soil moisture --------------------------------------------------
        soil_moisture_rz=state.theta_current,       # m3/m3 — live sim value

        # --- Weather / environment ------------------------------------------
        temperature_c=state.temperature_c,          # deg C — direct pass-through
        humidity_pct=state.relative_humidity_pct,   # % — direct pass-through
        wind_mps=state.wind_m_s,                    # m/s — direct pass-through
        radiation_mj_m2_day=state.radiation_mj_m2_day,  # MJ/m2/day — nullable

        # --- Rainfall -------------------------------------------------------
        rainfall_mm=state.rainfall_mm,              # mm — current timestep rainfall

        # --- Hydraulics (ACTUAL values — commanded vs actual distinction
        #     preserved for SCN-005 anomaly detection by later layers) -------
        flow_lpm=state.actual_flow_l_min,           # L/min — actual delivered flow
        pressure_bar=state.actual_pressure_bar,     # bar   — actual measured pressure

        # --- Provenance / quality -------------------------------------------
        source=TelemetrySource.SIMULATION,          # constant — always simulation
        quality=TelemetryQuality.VALID,             # simulation never drops/corrupts
    )
