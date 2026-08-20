"""
Layer 1 — Crop evapotranspiration (ETc) and Kc interpolation engine.

Implements two approved calculations from §3.3 of the Layer 1 specification:

1.  ETc = Kc × ET₀          (crop evapotranspiration)
2.  Kc(t) = Kc_start + ((t − t0) / duration) × (Kc_end − Kc_start)
            (linear Kc interpolation for transitional growth stages)

Source of truth: docs/05_LAYER1_SPEC.docx §3.3
Locked design:  single-Kc approach; stage-based selection; linear
                interpolation for transitions only.

Design rules:
  - Pure deterministic functions.  No network, DB, logging, or UI.
  - Reuses T1-02 ET0Result; does not duplicate atmospheric or ET₀ equations.
  - Kc values are supplied by the caller — no named-crop defaults here.
  - Returns typed results for consumption by T1-04 (water parameters).

Unit convention:
  ET₀     : mm/day
  ETc     : mm/day
  Kc      : dimensionless (0–∞ in principle; physically 0.1–1.4 for most crops)
  t       : days (non-negative integer or float for fractional days)
  t0      : days (start of the current stage)
  duration: days (positive)
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.layer1.et0 import ET0Result


# ---------------------------------------------------------------------------
# ETc result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ETcResult:
    """
    Output of the ETc calculation step.

    Preserves Kc and ET₀ alongside the final ETc value so that downstream
    modules (water-balance, feedback logger, Layer 2 feature engineering)
    have full traceability without re-computing anything.

    Source: docs/05_LAYER1_SPEC.docx §3.3, §8 (logging schema)
    """

    etc_mm_day: float
    """Crop evapotranspiration, mm/day.  ETc = Kc × ET₀."""

    Kc: float
    """Crop coefficient used for this timestep, dimensionless."""

    et0_mm_day: float
    """Reference evapotranspiration from T1-02, mm/day."""


# ---------------------------------------------------------------------------
# Kc interpolation
# ---------------------------------------------------------------------------


def interpolate_kc(
    t: float,
    t0: float,
    duration_days: float,
    Kc_start: float,
    Kc_end: float,
) -> float:
    """
    Linear Kc interpolation within a transitional growth stage.

    Equation (§3.3):
        Kc(t) = Kc_start + ((t − t0) / duration) × (Kc_end − Kc_start)

    Args:
        t             : Current day (same units as t0 and duration_days).
                        Must satisfy t0 <= t <= t0 + duration_days.
        t0            : Start day of the current stage (same units as t).
        duration_days : Length of the stage in days.  Must be > 0.
        Kc_start      : Kc at the beginning of the stage, dimensionless.
        Kc_end        : Kc at the end of the stage, dimensionless.

    Returns:
        Kc at day t, dimensionless.

    Notes:
        - At t == t0, returns Kc_start exactly.
        - At t == t0 + duration_days, returns Kc_end exactly.
        - For flat (non-transitional) stages set Kc_start == Kc_end;
          the result is constant regardless of t.
        - The spec restricts linear interpolation to transitional stages.
          The caller is responsible for passing appropriate Kc_start/Kc_end.

    Raises:
        ValueError: If duration_days is zero or negative (would cause
                    division by zero or physically nonsensical result).
                    The Layer 1 spec §7.1 requires duration to be a positive
                    integer; zero-length stages are invalid.
    """
    if duration_days <= 0:
        raise ValueError(
            f"duration_days must be positive, got {duration_days!r}. "
            "A zero-length stage is not defined by docs/05_LAYER1_SPEC.docx §7.1."
        )
    fraction = (t - t0) / duration_days
    return Kc_start + fraction * (Kc_end - Kc_start)


# ---------------------------------------------------------------------------
# ETc calculation
# ---------------------------------------------------------------------------


def calculate_etc(Kc: float, et0_mm_day: float) -> float:
    """
    Crop evapotranspiration from a Kc and ET₀.

    Equation (§3.3):
        ETc = Kc × ET₀

    Args:
        Kc          : Crop coefficient, dimensionless.
                      Supplied by the caller from crop configuration;
                      this function does not perform a crop table lookup.
        et0_mm_day  : Reference evapotranspiration, mm/day.

    Returns:
        ETc in mm/day.

    Notes:
        - A Kc of 0 produces ETc = 0 (bare soil with no transpiration).
        - Negative Kc is not physically meaningful; the spec does not
          define clamping here, so it is passed through.  The caller
          (configuration loader) is responsible for validating Kc bounds.
    """
    return Kc * et0_mm_day


def compute_etc(Kc: float, et0_result: ET0Result) -> ETcResult:
    """
    Compute ETc from a Kc and a completed ET0Result (T1-02 output).

    This is the standard entry point used by the full Layer 1 engine.
    It delegates to calculate_etc for the actual multiplication so that
    the core equation remains independently testable.

    Args:
        Kc         : Crop coefficient, dimensionless.
                     Supplied by the caller; not looked up inside this function.
        et0_result : ET0Result from T1-02 compute_et0.

    Returns:
        ETcResult with ETc, Kc, and ET₀ preserved.
    """
    etc = calculate_etc(Kc, et0_result.et0_mm_day)
    return ETcResult(
        etc_mm_day=etc,
        Kc=Kc,
        et0_mm_day=et0_result.et0_mm_day,
    )
