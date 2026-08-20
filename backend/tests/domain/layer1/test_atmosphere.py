"""
T1-01 — Tests for atmospheric variable calculations.

Tests cover:
  - saturation_vapour_pressure
  - actual_vapour_pressure
  - vapour_pressure_deficit
  - slope_saturation_vapour_pressure
  - atmospheric_pressure
  - psychrometric_constant
  - compute_atmospheric (the combined entry point)

Reference values are derived from the golden test fixture
(tests/fixtures/layer1_golden_test_cases.json) which is the
authoritative acceptance set for Layer 1.

The fixture file is never modified by these tests.

Source of truth: docs/05_LAYER1_SPEC.docx §3.1
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from app.domain.layer1.atmosphere import (
    actual_vapour_pressure,
    atmospheric_pressure,
    compute_atmospheric,
    psychrometric_constant,
    saturation_vapour_pressure,
    slope_saturation_vapour_pressure,
    vapour_pressure_deficit,
)
from app.domain.layer1.types import AtmosphericInput, AtmosphericResult

# ---------------------------------------------------------------------------
# Tolerance used across all floating-point comparisons.
# 1e-9 relative tolerance is tight enough to catch equation errors
# while allowing for platform floating-point differences.
# ---------------------------------------------------------------------------
REL_TOL = 1e-9

# ---------------------------------------------------------------------------
# Load golden fixture (read-only)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent.parent.parent
GOLDEN_PATH = REPO_ROOT.parent / "tests" / "fixtures" / "layer1_golden_test_cases.json"

with GOLDEN_PATH.open(encoding="utf-8") as _f:
    _GOLDEN_CASES: list[dict] = json.load(_f)

# Index by case ID for easy lookup
_GOLDEN: dict[str, dict] = {c["id"]: c for c in _GOLDEN_CASES}


# ===========================================================================
# saturation_vapour_pressure
# ===========================================================================


class TestSaturationVapourPressure:
    """Tests for es = 0.6108 × exp(17.27T / (T + 237.3))."""

    def test_golden_001_T30(self):
        """Golden case L1-GOLDEN-001: T=30°C → es ≈ 4.2431 kPa."""
        result = saturation_vapour_pressure(30.0)
        expected = _GOLDEN["L1-GOLDEN-001"]["expected"]["es_kpa"]
        assert math.isclose(result, expected, rel_tol=REL_TOL), (
            f"es(30°C): got {result}, expected {expected}"
        )

    def test_golden_002_T35(self):
        """Golden case L1-GOLDEN-002: T=35°C → es ≈ 5.6227 kPa."""
        result = saturation_vapour_pressure(35.0)
        expected = _GOLDEN["L1-GOLDEN-002"]["expected"]["es_kpa"]
        assert math.isclose(result, expected, rel_tol=REL_TOL)

    def test_golden_003_T28(self):
        """Golden case L1-GOLDEN-003: T=28°C → es ≈ 3.7799 kPa."""
        result = saturation_vapour_pressure(28.0)
        expected = _GOLDEN["L1-GOLDEN-003"]["expected"]["es_kpa"]
        assert math.isclose(result, expected, rel_tol=REL_TOL)

    def test_golden_005_T40(self):
        """Golden case L1-GOLDEN-005: T=40°C → es ≈ 7.3756 kPa."""
        result = saturation_vapour_pressure(40.0)
        expected = _GOLDEN["L1-GOLDEN-005"]["expected"]["es_kpa"]
        assert math.isclose(result, expected, rel_tol=REL_TOL)

    def test_zero_celsius(self):
        """At 0°C es should be approximately 0.6108 kPa (exp(0)=1 edge case)."""
        result = saturation_vapour_pressure(0.0)
        # es(0) = 0.6108 * exp(0) = 0.6108 exactly
        assert math.isclose(result, 0.6108, rel_tol=1e-6), (
            f"es(0°C) should be 0.6108, got {result}"
        )

    def test_increases_monotonically_with_temperature(self):
        """Higher temperature must always yield higher saturation pressure."""
        temperatures = [-5, 0, 10, 20, 30, 40, 50]
        pressures = [saturation_vapour_pressure(t) for t in temperatures]
        for i in range(len(pressures) - 1):
            assert pressures[i] < pressures[i + 1], (
                f"es not monotonic at T={temperatures[i]}→{temperatures[i+1]}"
            )

    def test_deterministic(self):
        """Same input must always produce the same output."""
        assert saturation_vapour_pressure(25.0) == saturation_vapour_pressure(25.0)


# ===========================================================================
# actual_vapour_pressure
# ===========================================================================


class TestActualVapourPressure:
    """Tests for ea = es × RH / 100."""

    def test_golden_001(self):
        """Golden case L1-GOLDEN-001: RH=50% → ea = es/2."""
        es = _GOLDEN["L1-GOLDEN-001"]["expected"]["es_kpa"]
        expected = _GOLDEN["L1-GOLDEN-001"]["expected"]["ea_kpa"]
        result = actual_vapour_pressure(es, 50.0)
        assert math.isclose(result, expected, rel_tol=REL_TOL)

    def test_golden_002(self):
        """Golden case L1-GOLDEN-002: RH=40%."""
        es = _GOLDEN["L1-GOLDEN-002"]["expected"]["es_kpa"]
        expected = _GOLDEN["L1-GOLDEN-002"]["expected"]["ea_kpa"]
        result = actual_vapour_pressure(es, 40.0)
        assert math.isclose(result, expected, rel_tol=REL_TOL)

    def test_golden_003(self):
        """Golden case L1-GOLDEN-003: RH=70%."""
        es = _GOLDEN["L1-GOLDEN-003"]["expected"]["es_kpa"]
        expected = _GOLDEN["L1-GOLDEN-003"]["expected"]["ea_kpa"]
        result = actual_vapour_pressure(es, 70.0)
        assert math.isclose(result, expected, rel_tol=REL_TOL)

    def test_rh_100_equals_es(self):
        """At 100% RH, ea must equal es (fully saturated air)."""
        es = 4.0
        result = actual_vapour_pressure(es, 100.0)
        assert math.isclose(result, es, rel_tol=REL_TOL)

    def test_rh_0_gives_zero(self):
        """At 0% RH, ea must be 0 (completely dry air)."""
        result = actual_vapour_pressure(3.5, 0.0)
        assert result == 0.0

    def test_deterministic(self):
        assert actual_vapour_pressure(4.0, 60.0) == actual_vapour_pressure(4.0, 60.0)


# ===========================================================================
# vapour_pressure_deficit
# ===========================================================================


class TestVapourPressureDeficit:
    """Tests for VPD = es − ea."""

    def test_positive_vpd_in_typical_conditions(self):
        """Typical daytime conditions: es > ea → VPD > 0."""
        es, ea = 4.24, 2.12
        result = vapour_pressure_deficit(es, ea)
        assert math.isclose(result, es - ea, rel_tol=REL_TOL)
        assert result > 0

    def test_zero_vpd_at_saturation(self):
        """Saturated air (RH=100%): VPD = 0."""
        es = 3.5
        result = vapour_pressure_deficit(es, es)
        assert result == 0.0

    def test_golden_001_derived(self):
        """Verify VPD from golden case 001 values is self-consistent."""
        es = _GOLDEN["L1-GOLDEN-001"]["expected"]["es_kpa"]
        ea = _GOLDEN["L1-GOLDEN-001"]["expected"]["ea_kpa"]
        result = vapour_pressure_deficit(es, ea)
        assert math.isclose(result, es - ea, rel_tol=REL_TOL)


# ===========================================================================
# slope_saturation_vapour_pressure
# ===========================================================================


class TestSlopeSaturationVapourPressure:
    """Tests for Δ = 4098 × es / (T + 237.3)²."""

    def test_golden_001_T30(self):
        """Golden case L1-GOLDEN-001: T=30, es from golden → Δ ≈ 0.2434 kPa/°C."""
        es = _GOLDEN["L1-GOLDEN-001"]["expected"]["es_kpa"]
        expected = _GOLDEN["L1-GOLDEN-001"]["expected"]["delta_kpa_per_c"]
        result = slope_saturation_vapour_pressure(30.0, es)
        assert math.isclose(result, expected, rel_tol=REL_TOL)

    def test_golden_002_T35(self):
        es = _GOLDEN["L1-GOLDEN-002"]["expected"]["es_kpa"]
        expected = _GOLDEN["L1-GOLDEN-002"]["expected"]["delta_kpa_per_c"]
        result = slope_saturation_vapour_pressure(35.0, es)
        assert math.isclose(result, expected, rel_tol=REL_TOL)

    def test_golden_003_T28(self):
        es = _GOLDEN["L1-GOLDEN-003"]["expected"]["es_kpa"]
        expected = _GOLDEN["L1-GOLDEN-003"]["expected"]["delta_kpa_per_c"]
        result = slope_saturation_vapour_pressure(28.0, es)
        assert math.isclose(result, expected, rel_tol=REL_TOL)

    def test_golden_005_T40(self):
        es = _GOLDEN["L1-GOLDEN-005"]["expected"]["es_kpa"]
        expected = _GOLDEN["L1-GOLDEN-005"]["expected"]["delta_kpa_per_c"]
        result = slope_saturation_vapour_pressure(40.0, es)
        assert math.isclose(result, expected, rel_tol=REL_TOL)

    def test_increases_with_temperature(self):
        """Δ increases with temperature — higher T means steeper e-T curve."""
        temps = [10, 20, 30, 40]
        deltas = [
            slope_saturation_vapour_pressure(t, saturation_vapour_pressure(t))
            for t in temps
        ]
        for i in range(len(deltas) - 1):
            assert deltas[i] < deltas[i + 1], "Δ must increase with temperature"

    def test_deterministic(self):
        es = saturation_vapour_pressure(25.0)
        assert (
            slope_saturation_vapour_pressure(25.0, es)
            == slope_saturation_vapour_pressure(25.0, es)
        )


# ===========================================================================
# atmospheric_pressure
# ===========================================================================


class TestAtmosphericPressure:
    """Tests for P = 101.3 × ((293 − 0.0065z) / 293)^5.26."""

    def test_golden_all_cases_elevation_900(self):
        """All five golden cases use elevation=900m → P ≈ 91.104 kPa."""
        for case_id, case in _GOLDEN.items():
            elevation = case["inputs"]["elevation_m"]
            expected = case["expected"]["pressure_kpa"]
            result = atmospheric_pressure(elevation)
            assert math.isclose(result, expected, rel_tol=REL_TOL), (
                f"{case_id}: P({elevation}m)={result}, expected {expected}"
            )

    def test_sea_level_is_101_3(self):
        """At sea level (z=0), P must equal exactly 101.3 kPa by construction."""
        result = atmospheric_pressure(0.0)
        assert math.isclose(result, 101.3, rel_tol=1e-9)

    def test_decreases_with_elevation(self):
        """Pressure must decrease monotonically as elevation increases."""
        elevations = [0, 500, 900, 1500, 3000]
        pressures = [atmospheric_pressure(z) for z in elevations]
        for i in range(len(pressures) - 1):
            assert pressures[i] > pressures[i + 1], (
                f"P not decreasing at z={elevations[i]}→{elevations[i+1]}"
            )

    def test_deterministic(self):
        assert atmospheric_pressure(900.0) == atmospheric_pressure(900.0)


# ===========================================================================
# psychrometric_constant
# ===========================================================================


class TestPsychrometricConstant:
    """Tests for γ = 0.000665 × P."""

    def test_golden_all_cases(self):
        """All five golden cases: γ must match the expected value exactly."""
        for case_id, case in _GOLDEN.items():
            P = case["expected"]["pressure_kpa"]
            expected = case["expected"]["gamma_kpa_per_c"]
            result = psychrometric_constant(P)
            assert math.isclose(result, expected, rel_tol=REL_TOL), (
                f"{case_id}: γ={result}, expected {expected}"
            )

    def test_linearly_proportional_to_pressure(self):
        """γ must scale linearly: γ(2P) = 2×γ(P)."""
        P = 91.0
        assert math.isclose(
            psychrometric_constant(2 * P),
            2 * psychrometric_constant(P),
            rel_tol=REL_TOL,
        )

    def test_deterministic(self):
        assert psychrometric_constant(91.104) == psychrometric_constant(91.104)


# ===========================================================================
# compute_atmospheric — combined entry point
# ===========================================================================


class TestComputeAtmospheric:
    """Tests for the composite compute_atmospheric function."""

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_golden_all_atmospheric_fields(self, case_id: str):
        """
        For each golden case, compute_atmospheric must match the expected
        es, ea, Δ, P and γ values within tight tolerance.

        VPD is not in the golden fixture as a standalone field, but it is
        verified to equal es - ea.
        """
        case = _GOLDEN[case_id]
        inp_data = case["inputs"]
        exp = case["expected"]

        inp = AtmosphericInput(
            T_c=inp_data["T_c"],
            RH_pct=inp_data["RH_pct"],
            elevation_m=inp_data["elevation_m"],
        )
        result: AtmosphericResult = compute_atmospheric(inp)

        assert math.isclose(result.es_kpa, exp["es_kpa"], rel_tol=REL_TOL), (
            f"{case_id} es: got {result.es_kpa}"
        )
        assert math.isclose(result.ea_kpa, exp["ea_kpa"], rel_tol=REL_TOL), (
            f"{case_id} ea: got {result.ea_kpa}"
        )
        assert math.isclose(result.delta_kpa_per_c, exp["delta_kpa_per_c"], rel_tol=REL_TOL), (
            f"{case_id} Δ: got {result.delta_kpa_per_c}"
        )
        assert math.isclose(result.pressure_kpa, exp["pressure_kpa"], rel_tol=REL_TOL), (
            f"{case_id} P: got {result.pressure_kpa}"
        )
        assert math.isclose(result.gamma_kpa_per_c, exp["gamma_kpa_per_c"], rel_tol=REL_TOL), (
            f"{case_id} γ: got {result.gamma_kpa_per_c}"
        )
        # VPD consistency check
        assert math.isclose(result.vpd_kpa, result.es_kpa - result.ea_kpa, rel_tol=REL_TOL), (
            f"{case_id} VPD inconsistency"
        )

    def test_returns_atmospheric_result_type(self):
        """compute_atmospheric must return an AtmosphericResult instance."""
        inp = AtmosphericInput(T_c=25.0, RH_pct=60.0, elevation_m=0.0)
        result = compute_atmospheric(inp)
        assert isinstance(result, AtmosphericResult)

    def test_frozen_result_is_immutable(self):
        """AtmosphericResult is a frozen dataclass — mutation must raise."""
        inp = AtmosphericInput(T_c=25.0, RH_pct=60.0, elevation_m=0.0)
        result = compute_atmospheric(inp)
        with pytest.raises((AttributeError, TypeError)):
            result.es_kpa = 99.0  # type: ignore[misc]

    def test_deterministic_on_repeated_call(self):
        """Same input must produce identical output on repeated calls."""
        inp = AtmosphericInput(T_c=32.0, RH_pct=55.0, elevation_m=450.0)
        r1 = compute_atmospheric(inp)
        r2 = compute_atmospheric(inp)
        assert r1 == r2
