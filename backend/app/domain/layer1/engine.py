"""
Layer 1 — Unified agronomic engine entry point.

This module is ORCHESTRATION ONLY.

It composes T1-01 through T1-05 in the correct mathematical dependency
order and returns a single typed Layer1Result.  It does not implement any
new agronomic equations.

Dependency chain (§3 of docs/05_LAYER1_SPEC.docx):

  Layer1Input
       │
       ▼
  T1-01  compute_atmospheric  →  AtmosphericResult
       │
       ▼
  T1-02  compute_et0          →  ET0Result
       │
       ▼
  T1-03  compute_etc          →  ETcResult
       │
       ▼
  T1-04  compute_water_parameters  →  WaterParametersResult
       │
       ▼
  T1-05  compute_root_zone    →  RootZoneResult
       │
       ▼
  Layer1Result   ←  flat projection of all sub-results + input echoes

Design rules:
  - No new equations.
  - No silent defaults.
  - Errors from sub-modules propagate unchanged.
  - No database, network, simulation, or actuation logic.
  - Deterministic on identical input.

Source of truth: docs/05_LAYER1_SPEC.docx §3, §8
Agent contract:  AGENTS.md §5, §16
"""

from __future__ import annotations

from app.domain.layer1.atmosphere import compute_atmospheric
from app.domain.layer1.et0 import compute_et0
from app.domain.layer1.etc import compute_etc
from app.domain.layer1.root_zone import compute_root_zone
from app.domain.layer1.types import (
    AtmosphericInput,
    Layer1Input,
    Layer1Result,
)
from app.domain.layer1.water_parameters import compute_water_parameters


def compute_layer1(inp: Layer1Input) -> Layer1Result:
    """
    Run one complete Layer 1 deterministic agronomic calculation cycle.

    Orchestrates the T1-01 → T1-05 pipeline and returns a flat Layer1Result
    containing every intermediate and final value required for:
      - simulation state update
      - Layer 2 feature engineering
      - decision engine
      - feedback logging
      - API serialisation

    Args:
        inp: Complete Layer1Input for one timestep.  All sub-fields are
             consumed; see Layer1Input docstring for unit requirements.

    Returns:
        Layer1Result with atmospheric state, ET₀, ETc, TAW/p/RAW/θ_critical,
        root-zone depletion, trigger decision, and full irrigation prescription.

    Raises:
        ValueError: If any sub-module detects an invalid input (e.g. zero
                    application efficiency when irrigation is triggered, non-
                    positive flow rate when irrigation is triggered).  Errors
                    are NOT suppressed — they propagate to the caller so the
                    simulation/API layer can handle them explicitly.
    """
    # ------------------------------------------------------------------ T1-01
    # Atmospheric variables.
    # compute_atmospheric accepts AtmosphericInput (T, RH, elevation).
    # Those three fields are present on Layer1Input.et0_input.
    atm = compute_atmospheric(
        AtmosphericInput(
            T_c=inp.et0_input.T_c,
            RH_pct=inp.et0_input.RH_pct,
            elevation_m=inp.et0_input.elevation_m,
        )
    )

    # ------------------------------------------------------------------ T1-02
    # Reference evapotranspiration (ET₀, FAO-56 Penman-Monteith).
    et0 = compute_et0(inp.et0_input)

    # ------------------------------------------------------------------ T1-03
    # Crop evapotranspiration (ETc = Kc × ET₀).
    etc = compute_etc(Kc=inp.crop.Kc, et0_result=et0)

    # ------------------------------------------------------------------ T1-04
    # Root-zone water availability parameters: TAW, adjusted p, RAW, θ_critical.
    wp = compute_water_parameters(
        theta_FC=inp.soil.theta_FC,
        theta_WP=inp.soil.theta_WP,
        Zr_m=inp.soil.root_depth_m,
        p_table=inp.crop.p_table,
        ETc_mm_day=etc.etc_mm_day,
    )

    # ------------------------------------------------------------------ T1-05
    # Root-zone state and irrigation prescription.
    rz = compute_root_zone(
        theta_current=inp.theta_current,
        theta_FC=inp.soil.theta_FC,
        theta_WP=inp.soil.theta_WP,
        Zr_m=inp.soil.root_depth_m,
        TAW_mm=wp.TAW_mm,
        RAW_mm=wp.RAW_mm,
        application_efficiency=inp.soil.application_efficiency,
        field_area_m2=inp.soil.zone_area_m2,
        flow_l_per_min=inp.soil.flow_rate_l_min,
    )

    # -------------------------------------------------------- Flat projection
    # All intermediate results are flattened into Layer1Result for traceability.
    # No calculations are performed here — only field projection.
    return Layer1Result(
        # Atmospheric (T1-01)
        es_kpa=atm.es_kpa,
        ea_kpa=atm.ea_kpa,
        vpd_kpa=atm.vpd_kpa,
        delta_kpa_per_c=atm.delta_kpa_per_c,
        pressure_kpa=atm.pressure_kpa,
        gamma_kpa_per_c=atm.gamma_kpa_per_c,
        # ET (T1-02 / T1-03)
        et0_mm_day=et0.et0_mm_day,
        etc_mm_day=etc.etc_mm_day,
        Kc=inp.crop.Kc,
        # Root-zone capacity (T1-04)
        taw_mm=wp.TAW_mm,
        p=wp.p,
        raw_mm=wp.RAW_mm,
        theta_critical_m3_m3=wp.theta_critical,
        # Root-zone state (T1-05)
        depletion_mm=rz.Dr_mm,
        # Decision (T1-05)
        irrigation_trigger=rz.irrigation_trigger,
        net_irrigation_mm=rz.I_net_mm,
        gross_irrigation_mm=rz.I_gross_mm,
        # Prescription (T1-05)
        water_volume_litres=rz.water_volume_litres,
        valve_runtime_minutes=rz.valve_runtime_minutes,
        # Soil / zone input echoes (§8 traceability)
        theta_FC=inp.soil.theta_FC,
        theta_WP=inp.soil.theta_WP,
        Zr_m=inp.soil.root_depth_m,
        theta_current=inp.theta_current,
        field_area_m2=inp.soil.zone_area_m2,
        application_efficiency=inp.soil.application_efficiency,
        flow_rate_l_min=inp.soil.flow_rate_l_min,
    )
