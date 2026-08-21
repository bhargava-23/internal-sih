"""
Simulation → Layer 1 adapter.

Converts a SimulationState (produced by T2-01) plus zone/crop configuration
into a Layer1Input, then runs compute_layer1() and returns both results.

This is an INTEGRATION ADAPTER ONLY.

It does NOT:
  - implement ET₀, Kc, ETc, TAW, RAW, depletion, or any agronomic equation;
  - duplicate any calculation from Layer 1;
  - contain simulation stepping logic;
  - contain decision logic;
  - access the database or network.

Source of truth:
  docs/02_SIMULATION_PROTOTYPE_SPEC.docx §7 (integration pipeline)
  docs/05_LAYER1_SPEC.docx §2 (inputs)
  AGENTS.md §5 (pipeline order)

Missing-input rationale
-----------------------

SimulationState carries all fields produced by the simulation engine.
Three groups of Layer 1 inputs are NOT in SimulationState because they are
zone/agronomic configuration, not runtime sensor readings:

  1. elevation_m          — site elevation for atmospheric pressure / ET₀.
                            Not a sensor reading; it is a fixed site parameter.
  2. Kc, p_table          — crop coefficient and allowable depletion fraction.
                            These are stage-specific agronomic config; the
                            simulation does not own crop tables.
  3. application_efficiency, flow_rate_l_min
                            — irrigation system parameters; vary by zone
                            hardware, not by field conditions.

These are supplied by the caller via ZoneConfig (defined below).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.layer1.engine import compute_layer1
from app.domain.layer1.types import (
    CropConfig,
    ET0Input,
    Layer1Input,
    Layer1Result,
    SoilConfig,
)
from app.domain.simulation.state import SimulationState


# ---------------------------------------------------------------------------
# Zone configuration (agronomic + site parameters not held in SimulationState)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ZoneConfig:
    """
    Zone-level agronomic and site configuration supplied by the caller.

    These values are NOT sensor readings — they are fixed or stage-varying
    configuration parameters that the simulation engine does not own.

    All five V1 scenarios use the same crop ('tomato', 'flowering') so the
    caller supplies Kc and p_table for the current growth stage.

    The caller is responsible for updating these values when the growth
    stage changes (e.g. between scenarios or over a multi-day simulation).

    Source: docs/05_LAYER1_SPEC.docx §7.1, §7.2
    """

    Kc: float
    """Crop coefficient for the current growth stage, dimensionless."""

    p_table: float
    """Baseline allowable depletion fraction from FAO crop table, 0–1."""

    elevation_m: float
    """Site elevation above mean sea level, m.
    Used by ET₀ to estimate atmospheric pressure.
    Not a sensor reading; a fixed site parameter.
    """

    application_efficiency: float = 0.90
    """System application efficiency E_a, dimensionless (0–1)."""

    flow_rate_l_min: float = 20.0
    """Nominal zone flow rate, L/min."""


# ---------------------------------------------------------------------------
# Integration result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SimLayer1Result:
    """
    Combined result of one simulation-to-Layer-1 integration step.

    Exposes:
      - simulation_state  : the SimulationState that was used as input
      - layer1_result     : the full Layer1Result computed from it

    Downstream consumers (ML pipeline, decision engine, API, dashboard) can
    access every intermediate agronomic value through layer1_result without
    needing to re-run Layer 1.
    """

    simulation_state: SimulationState
    """The SimulationState that was the source of this computation."""

    layer1_result: Layer1Result
    """Complete Layer 1 agronomic result for this timestep."""


# ---------------------------------------------------------------------------
# Adapter — explicit unit-annotated mapping
# ---------------------------------------------------------------------------


def simulation_state_to_layer1_input(
    state: SimulationState,
    zone: ZoneConfig,
) -> Layer1Input:
    """
    Map a SimulationState to a Layer1Input.

    Every field assignment is explicit and unit-annotated so that a reader
    can verify the mapping without running the code.

    No agronomic equations are computed here.
    No simulation logic is duplicated here.

    Args:
        state: Current simulation state for this timestep.
        zone:  Zone-level agronomic and site configuration.

    Returns:
        Layer1Input ready to pass to compute_layer1().

    Field mapping
    -------------
    SimulationState.temperature_c          → ET0Input.T_c            [°C]
    SimulationState.relative_humidity_pct  → ET0Input.RH_pct         [%]
    SimulationState.wind_m_s               → ET0Input.wind_m_s       [m/s]
    SimulationState.radiation_mj_m2_day    → ET0Input.Rn_MJ_m2_day   [MJ/m²/day]
    ZoneConfig.elevation_m                 → ET0Input.elevation_m    [m]

    SimulationState.theta_FC               → SoilConfig.theta_FC     [m³/m³]
    SimulationState.theta_WP               → SoilConfig.theta_WP     [m³/m³]
    SimulationState.root_zone_depth_m      → SoilConfig.root_depth_m [m]
    SimulationState.field_area_m2          → SoilConfig.zone_area_m2 [m²]
    ZoneConfig.application_efficiency     → SoilConfig.application_efficiency [-]
    ZoneConfig.flow_rate_l_min             → SoilConfig.flow_rate_l_min [L/min]

    ZoneConfig.Kc                          → CropConfig.Kc           [-]
    ZoneConfig.p_table                     → CropConfig.p_table      [-]

    SimulationState.theta_current          → Layer1Input.theta_current [m³/m³]
    SimulationState.rainfall_mm            → Layer1Input.effective_rain_mm [mm]
    """
    return Layer1Input(
        et0_input=ET0Input(
            T_c=state.temperature_c,            # °C — direct pass-through
            RH_pct=state.relative_humidity_pct, # % — direct pass-through
            wind_m_s=state.wind_m_s,            # m/s — direct pass-through
            Rn_MJ_m2_day=state.radiation_mj_m2_day,  # MJ/m²/day — direct
            elevation_m=zone.elevation_m,       # m — site config
        ),
        soil=SoilConfig(
            theta_FC=state.theta_FC,            # m³/m³ — from sim state
            theta_WP=state.theta_WP,            # m³/m³ — from sim state
            root_depth_m=state.root_zone_depth_m,    # m — from sim state
            zone_area_m2=state.field_area_m2,   # m² — from sim state
            application_efficiency=zone.application_efficiency,  # zone config
            flow_rate_l_min=zone.flow_rate_l_min,    # zone config
        ),
        crop=CropConfig(
            Kc=zone.Kc,         # zone/stage config — not invented
            p_table=zone.p_table,  # zone/stage config — not invented
        ),
        theta_current=state.theta_current,       # m³/m³ — live sensor/sim value
        effective_rain_mm=state.rainfall_mm,     # mm — current timestep rainfall
    )


def run_layer1_for_state(
    state: SimulationState,
    zone: ZoneConfig,
) -> SimLayer1Result:
    """
    Convert a SimulationState to Layer1Input and run compute_layer1().

    This is the primary entry point for the simulation–Layer 1 integration.
    It is a thin orchestration call; all computation is in compute_layer1().

    Args:
        state: Current simulation state for this timestep.
        zone:  Zone-level agronomic and site configuration.

    Returns:
        SimLayer1Result containing both the simulation state and the full
        Layer 1 agronomic result.

    Raises:
        ValueError: If Layer 1 detects an invalid input (e.g. zero
                    application efficiency when irrigation is triggered).
                    Errors are not suppressed.
    """
    layer1_input = simulation_state_to_layer1_input(state, zone)
    layer1_result = compute_layer1(layer1_input)
    return SimLayer1Result(
        simulation_state=state,
        layer1_result=layer1_result,
    )
