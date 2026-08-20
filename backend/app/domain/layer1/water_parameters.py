"""
Layer 1 — Root-zone soil water availability parameters.

Implements four deterministic calculations from docs/05_LAYER1_SPEC.docx §3.4:

1.  TAW  = 1000 × (θ_FC − θ_WP) × Zr
2.  p    = clip(p_table + 0.04 × (5 − ETc), 0.1, 0.8)
3.  RAW  = p × TAW
4.  θ_critical = θ_FC − p × (θ_FC − θ_WP)

These values feed the irrigation trigger (T1-05) and root-zone state
calculations (T1-05).  This module does NOT implement the trigger, the
water balance, or any actuation logic.

Source of truth: docs/05_LAYER1_SPEC.docx §3.4
Locked design:  pure functional, typed inputs/outputs, no side effects.

Unit convention:
  θ_FC, θ_WP, θ_critical : m³/m³  (volumetric water content fractions)
  Zr                      : m      (effective root-zone depth)
  TAW, RAW                : mm     (millimetres of plant-available water)
  ETc                     : mm/day (crop evapotranspiration)
  p, p_table              : dimensionless (0–1 allowable depletion fraction)

Numeric p_table values are supplied by the caller from an approved agronomic
source.  This module does not contain any default p_table for any named crop.
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Clipping bounds — locked by the Layer 1 specification §3.4
# ---------------------------------------------------------------------------

_P_MIN: float = 0.1
_P_MAX: float = 0.8


# ---------------------------------------------------------------------------
# Water parameters result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WaterParametersResult:
    """
    Output of the root-zone soil water availability calculation.

    Carries all four computed values plus the adjusted p so that downstream
    modules (trigger, water balance, Layer 2 features) have complete
    traceability without re-computing.

    Source: docs/05_LAYER1_SPEC.docx §3.4, §8 (logging schema)
    """

    TAW_mm: float
    """Total plant-available water in the root zone, mm.
    TAW = 1000 × (θ_FC − θ_WP) × Zr
    """

    p: float
    """ETc-adjusted allowable depletion fraction, dimensionless.
    Clipped to [0.1, 0.8] per the Layer 1 specification §3.4.
    """

    RAW_mm: float
    """Readily available water, mm.
    RAW = p × TAW
    """

    theta_critical: float
    """Critical volumetric water content threshold, m³/m³.
    θ_critical = θ_FC − p × (θ_FC − θ_WP)

    When θ_current drops to or below this value, Dr ≥ RAW and an
    irrigation trigger condition is met (evaluated in T1-05).
    """

    # Input echo — kept for traceability in logs and Layer 2 features
    theta_FC: float
    """Field-capacity volumetric water content, m³/m³ (input echo)."""

    theta_WP: float
    """Wilting-point volumetric water content, m³/m³ (input echo)."""

    Zr_m: float
    """Effective root-zone depth, m (input echo)."""

    p_table: float
    """Unadjusted tabular depletion fraction supplied by the caller (input echo)."""

    ETc_mm_day: float
    """Crop evapotranspiration used for the p adjustment, mm/day (input echo)."""


# ---------------------------------------------------------------------------
# Individual calculation functions (independently testable)
# ---------------------------------------------------------------------------


def calculate_taw(theta_FC: float, theta_WP: float, Zr_m: float) -> float:
    """
    Total available water in the root zone.

    Equation (§3.4):
        TAW = 1000 × (θ_FC − θ_WP) × Zr

    Args:
        theta_FC : Field-capacity volumetric water content, m³/m³.
        theta_WP : Wilting-point volumetric water content, m³/m³.
        Zr_m     : Effective root-zone depth, m.

    Returns:
        TAW in mm.

    Note:
        The 1000 factor converts m³/m³ × m = m to mm
        (1 m depth of water = 1000 mm).
    """
    return 1000.0 * (theta_FC - theta_WP) * Zr_m


def calculate_p(p_table: float, ETc_mm_day: float) -> float:
    """
    ETc-adjusted allowable depletion fraction.

    Equation (§3.4):
        p = clip(p_table + 0.04 × (5 − ETc), 0.1, 0.8)

    The adjustment reduces p (increases the sensitivity to moisture stress)
    when ETc is high, and raises p when ETc is low — following the
    FAO-56 Annex 8 tabular correction approach.

    Args:
        p_table     : Baseline depletion fraction from the crop configuration,
                      dimensionless.  Supplied by the caller; not derived here.
        ETc_mm_day  : Crop evapotranspiration, mm/day.

    Returns:
        Adjusted depletion fraction, clipped to [0.1, 0.8].
    """
    p_adjusted = p_table + 0.04 * (5.0 - ETc_mm_day)
    return max(_P_MIN, min(_P_MAX, p_adjusted))


def calculate_raw(p: float, TAW_mm: float) -> float:
    """
    Readily available water.

    Equation (§3.4):
        RAW = p × TAW

    Args:
        p      : Adjusted depletion fraction (output of calculate_p), dimensionless.
        TAW_mm : Total available water, mm.

    Returns:
        RAW in mm.
    """
    return p * TAW_mm


def calculate_theta_critical(
    theta_FC: float, p: float, theta_WP: float
) -> float:
    """
    Critical volumetric moisture threshold corresponding to the RAW trigger point.

    Equation (§3.4):
        θ_critical = θ_FC − p × (θ_FC − θ_WP)

    When the root-zone soil moisture θ_current falls to or below this value,
    the root-zone depletion Dr reaches RAW and the irrigation trigger
    condition is satisfied (evaluated by T1-05).

    Args:
        theta_FC : Field-capacity volumetric water content, m³/m³.
        p        : Adjusted depletion fraction (output of calculate_p), dimensionless.
        theta_WP : Wilting-point volumetric water content, m³/m³.

    Returns:
        θ_critical in m³/m³.
    """
    return theta_FC - p * (theta_FC - theta_WP)


# ---------------------------------------------------------------------------
# High-level entry point
# ---------------------------------------------------------------------------


def compute_water_parameters(
    theta_FC: float,
    theta_WP: float,
    Zr_m: float,
    p_table: float,
    ETc_mm_day: float,
) -> WaterParametersResult:
    """
    Compute all four root-zone water availability parameters from soil and
    crop-configuration inputs.

    Delegates to the individual functions above so that each equation
    remains independently testable.  No equations are duplicated.

    Args:
        theta_FC    : Field-capacity volumetric water content, m³/m³.
        theta_WP    : Wilting-point volumetric water content, m³/m³.
        Zr_m        : Effective root-zone depth, m.
        p_table     : Unadjusted tabular depletion fraction from crop config,
                      dimensionless.  Supplied by the caller.
        ETc_mm_day  : Crop evapotranspiration, mm/day.  Produced by T1-03.

    Returns:
        WaterParametersResult with TAW, p, RAW, θ_critical, and all
        input echoes for traceability.
    """
    taw = calculate_taw(theta_FC, theta_WP, Zr_m)
    p = calculate_p(p_table, ETc_mm_day)
    raw = calculate_raw(p, taw)
    theta_crit = calculate_theta_critical(theta_FC, p, theta_WP)

    return WaterParametersResult(
        TAW_mm=taw,
        p=p,
        RAW_mm=raw,
        theta_critical=theta_crit,
        theta_FC=theta_FC,
        theta_WP=theta_WP,
        Zr_m=Zr_m,
        p_table=p_table,
        ETc_mm_day=ETc_mm_day,
    )
