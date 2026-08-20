"""
Layer 1 — Daily FAO-56 Penman-Monteith reference evapotranspiration (ET₀).

Implements the locked daily ET₀ equation from the Layer 1 specification §3.2.

Source of truth: docs/05_LAYER1_SPEC.docx §3.2
Locked equation — do not substitute an alternative formulation.

Design rules:
  - Pure deterministic calculation.  No network, DB, logging, or UI.
  - Reuses T1-01 atmospheric primitives; does not duplicate their equations.
  - Returns a typed result that T1-03 (ETc) can consume directly.

Unit convention (FAO-56 / Layer 1 spec):
  T        : °C
  u2       : m/s  (wind speed at 2 m)
  Rn       : MJ/m²/day
  G        : MJ/m²/day  (soil heat flux; 0 for daily timestep)
  es       : kPa
  ea       : kPa
  Δ        : kPa/°C
  γ        : kPa/°C
  ET₀      : mm/day
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.layer1.atmosphere import compute_atmospheric
from app.domain.layer1.types import AtmosphericInput, AtmosphericResult, ET0Input


# ---------------------------------------------------------------------------
# ET₀ result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ET0Result:
    """
    Output of the daily FAO-56 Penman-Monteith ET₀ calculation.

    Carries both the final ET₀ value and all intermediate atmospheric
    quantities so that the caller (T1-03 ETc, logging, tests) has complete
    traceability without re-computing anything.
    """

    et0_mm_day: float
    """Reference evapotranspiration, mm/day."""

    # Atmospheric intermediates (from T1-01) — preserved for traceability
    es_kpa: float
    """Saturation vapour pressure, kPa."""

    ea_kpa: float
    """Actual vapour pressure, kPa."""

    vpd_kpa: float
    """Vapour pressure deficit, kPa."""

    delta_kpa_per_c: float
    """Slope of the saturation vapour-pressure curve (Δ), kPa/°C."""

    pressure_kpa: float
    """Atmospheric pressure from elevation, kPa."""

    gamma_kpa_per_c: float
    """Psychrometric constant (γ), kPa/°C."""

    G_MJ_m2_day: float
    """Soil heat flux density, MJ/m²/day.
    Zero for the daily prototype convention (Layer 1 spec §3.2).
    Stored explicitly so future sub-daily implementations can override it.
    """


# ---------------------------------------------------------------------------
# Core ET₀ calculation
# ---------------------------------------------------------------------------


def calculate_et0(
    T_c: float,
    u2_m_s: float,
    Rn_MJ_m2_day: float,
    es_kpa: float,
    ea_kpa: float,
    delta_kpa_per_c: float,
    gamma_kpa_per_c: float,
    G_MJ_m2_day: float = 0.0,
) -> float:
    """
    FAO-56 Penman-Monteith daily ET₀.

    Equation (§3.2):
        ET₀ = [0.408·Δ·(Rn − G) + γ·(900/(T+273))·u2·(es−ea)]
              / [Δ + γ·(1 + 0.34·u2)]

    Args:
        T_c             : Mean daily air temperature, °C.
        u2_m_s          : Wind speed at 2 m height, m/s.
        Rn_MJ_m2_day    : Net radiation at crop surface, MJ/m²/day.
        es_kpa          : Saturation vapour pressure, kPa.
        ea_kpa          : Actual vapour pressure, kPa.
        delta_kpa_per_c : Slope of saturation vapour-pressure curve (Δ), kPa/°C.
        gamma_kpa_per_c : Psychrometric constant (γ), kPa/°C.
        G_MJ_m2_day     : Soil heat flux density, MJ/m²/day.
                          Default 0 per the daily prototype convention (§3.2).

    Returns:
        ET₀ in mm/day.

    Note:
        The 0.408 factor converts MJ/m²/day to mm/day via the inverse of the
        latent heat of vaporisation for water at ~20 °C (λ ≈ 2.45 MJ/kg,
        ρ_w = 1000 kg/m³ → 1/λ ≈ 0.408 mm/MJ·m²).
        The 900 coefficient and (T + 273) denominator come from the
        wind-function term of the FAO Penman-Monteith equation (FAO-56 eq. 6).
    """
    numerator = (
        0.408 * delta_kpa_per_c * (Rn_MJ_m2_day - G_MJ_m2_day)
        + gamma_kpa_per_c * (900.0 / (T_c + 273.0)) * u2_m_s * (es_kpa - ea_kpa)
    )
    denominator = delta_kpa_per_c + gamma_kpa_per_c * (1.0 + 0.34 * u2_m_s)
    return numerator / denominator


# ---------------------------------------------------------------------------
# High-level entry point — accepts ET0Input and returns ET0Result
# ---------------------------------------------------------------------------


def compute_et0(inp: ET0Input) -> ET0Result:
    """
    Compute daily FAO-56 ET₀ from a typed ET0Input.

    Internally delegates atmospheric sub-calculations to T1-01
    (compute_atmospheric) and then applies the locked ET₀ equation.

    No equations from T1-01 are duplicated here.

    Args:
        inp: ET0Input containing temperature, humidity, wind, radiation,
             and site elevation.

    Returns:
        ET0Result with ET₀ in mm/day and all intermediate values.
    """
    # Step 1 — Compute all six atmospheric variables via T1-01
    atm_inp = AtmosphericInput(
        T_c=inp.T_c,
        RH_pct=inp.RH_pct,
        elevation_m=inp.elevation_m,
    )
    atm: AtmosphericResult = compute_atmospheric(atm_inp)

    # Step 2 — Apply the daily ET₀ equation (G = 0 per spec §3.2)
    G = 0.0  # daily prototype convention; Layer 1 spec §3.2
    et0 = calculate_et0(
        T_c=inp.T_c,
        u2_m_s=inp.wind_m_s,
        Rn_MJ_m2_day=inp.Rn_MJ_m2_day,
        es_kpa=atm.es_kpa,
        ea_kpa=atm.ea_kpa,
        delta_kpa_per_c=atm.delta_kpa_per_c,
        gamma_kpa_per_c=atm.gamma_kpa_per_c,
        G_MJ_m2_day=G,
    )

    return ET0Result(
        et0_mm_day=et0,
        es_kpa=atm.es_kpa,
        ea_kpa=atm.ea_kpa,
        vpd_kpa=atm.vpd_kpa,
        delta_kpa_per_c=atm.delta_kpa_per_c,
        pressure_kpa=atm.pressure_kpa,
        gamma_kpa_per_c=atm.gamma_kpa_per_c,
        G_MJ_m2_day=G,
    )
