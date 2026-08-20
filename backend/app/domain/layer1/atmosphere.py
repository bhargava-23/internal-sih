"""
Layer 1 — Atmospheric variable calculations (§3.1).

Implements the six atmospheric sub-calculations that feed into the
FAO Penman-Monteith ET₀ equation.

Source of truth: docs/05_LAYER1_SPEC.docx §3.1
Locked equations — do not substitute alternative formulations.

All functions are:
  - pure (no side effects, no global state)
  - deterministic
  - independent of the database, network, and frontend

Unit convention (matches FAO-56 / Layer 1 spec):
  Temperature        : °C
  Relative humidity  : % (0–100)
  Elevation          : m
  Vapour pressure    : kPa
  Δ (delta)          : kPa/°C
  Atmospheric P      : kPa
  γ (gamma)          : kPa/°C
"""

from __future__ import annotations

import math

from app.domain.layer1.types import AtmosphericInput, AtmosphericResult


# ---------------------------------------------------------------------------
# Individual atmospheric functions
# Each function is kept small and independently testable.
# ---------------------------------------------------------------------------


def saturation_vapour_pressure(T_c: float) -> float:
    """
    Saturation vapour pressure at temperature T.

    Equation (§3.1):
        es = 0.6108 × exp(17.27 × T / (T + 237.3))

    Args:
        T_c: Air temperature, °C.

    Returns:
        es: Saturation vapour pressure, kPa.

    Note:
        The 0.6108 coefficient converts from the original Tetens
        formula to kPa units (FAO-56 eq. 11).
        Valid for typical agricultural temperature range (−10 °C to 50 °C).
    """
    return 0.6108 * math.exp(17.27 * T_c / (T_c + 237.3))


def actual_vapour_pressure(es_kpa: float, RH_pct: float) -> float:
    """
    Actual vapour pressure from relative humidity.

    Equation (§3.1):
        ea = es × RH / 100

    Args:
        es_kpa: Saturation vapour pressure, kPa.
        RH_pct: Relative humidity, % (0–100).

    Returns:
        ea: Actual vapour pressure, kPa.
    """
    return es_kpa * RH_pct / 100.0


def vapour_pressure_deficit(es_kpa: float, ea_kpa: float) -> float:
    """
    Vapour pressure deficit.

    Equation (§3.1):
        VPD = es − ea

    Args:
        es_kpa: Saturation vapour pressure, kPa.
        ea_kpa: Actual vapour pressure, kPa.

    Returns:
        VPD: Vapour pressure deficit, kPa.
        A non-negative value physically; negative values indicate
        supersaturation and are passed through without clamping
        (let the caller decide — the spec does not define clamping here).
    """
    return es_kpa - ea_kpa


def slope_saturation_vapour_pressure(T_c: float, es_kpa: float) -> float:
    """
    Slope of the saturation vapour-pressure curve at temperature T.

    Equation (§3.1):
        Δ = 4098 × es / (T + 237.3)²

    Args:
        T_c: Air temperature, °C.
        es_kpa: Saturation vapour pressure at T, kPa.
                Passed as a parameter to avoid recomputing es; the ET₀
                caller already has es available and this keeps functions
                composable without duplicate computation.

    Returns:
        Δ (delta): Slope of the saturation vapour-pressure curve, kPa/°C.
    """
    return 4098.0 * es_kpa / (T_c + 237.3) ** 2


def atmospheric_pressure(elevation_m: float) -> float:
    """
    Atmospheric pressure estimated from site elevation.

    Equation (§3.1):
        P = 101.3 × ((293 − 0.0065z) / 293)^5.26

    Args:
        elevation_m: Site elevation above mean sea level, m.

    Returns:
        P: Estimated atmospheric pressure, kPa.

    Note:
        Used when a pressure sensor is not available.
        At sea level (z=0): P ≈ 101.3 kPa (by construction).
        The exponent 5.26 encodes the dry-adiabatic lapse rate assumption
        from FAO-56 eq. 7.
    """
    return 101.3 * ((293.0 - 0.0065 * elevation_m) / 293.0) ** 5.26


def psychrometric_constant(pressure_kpa: float) -> float:
    """
    Psychrometric constant from atmospheric pressure.

    Equation (§3.1):
        γ = 0.000665 × P

    Args:
        pressure_kpa: Atmospheric pressure, kPa.

    Returns:
        γ (gamma): Psychrometric constant, kPa/°C.

    Note:
        The 0.000665 factor combines the specific heat of air, latent heat
        of vaporisation and ratio of molecular weights (FAO-56 eq. 8).
        It is dimensionally correct and independent of temperature for
        the daily FAO calculation.
    """
    return 0.000665 * pressure_kpa


# ---------------------------------------------------------------------------
# Convenience function — compute all six variables in one call
# ---------------------------------------------------------------------------


def compute_atmospheric(inp: AtmosphericInput) -> AtmosphericResult:
    """
    Compute all six atmospheric variables for a given weather observation.

    This is the standard entry point used by the ET₀ module (T1-02).
    Each sub-calculation is delegated to its individual function so that
    they can also be called independently in tests.

    Args:
        inp: AtmosphericInput containing temperature, relative humidity,
             and site elevation.

    Returns:
        AtmosphericResult with all six calculated variables.
    """
    es = saturation_vapour_pressure(inp.T_c)
    ea = actual_vapour_pressure(es, inp.RH_pct)
    vpd = vapour_pressure_deficit(es, ea)
    delta = slope_saturation_vapour_pressure(inp.T_c, es)
    pressure = atmospheric_pressure(inp.elevation_m)
    gamma = psychrometric_constant(pressure)

    return AtmosphericResult(
        es_kpa=es,
        ea_kpa=ea,
        vpd_kpa=vpd,
        delta_kpa_per_c=delta,
        pressure_kpa=pressure,
        gamma_kpa_per_c=gamma,
    )
