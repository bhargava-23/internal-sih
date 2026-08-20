"""
T1-02 — Tests for the daily FAO-56 Penman-Monteith ET₀ calculation.

Tests cover:
  - calculate_et0 (low-level, pre-computed atmospheric inputs)
  - compute_et0   (high-level, accepts ET0Input and integrates T1-01)

Reference values are taken directly from the golden test fixture
(tests/fixtures/layer1_golden_test_cases.json).  The fixture is never
modified here.  Where specific ET₀ intermediate values are needed that are
not in the fixture, they are computed from the approved equations and clearly
labeled as DERIVED.

Source of truth: docs/05_LAYER1_SPEC.docx §3.2
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from app.domain.layer1.et0 import ET0Result, calculate_et0, compute_et0
from app.domain.layer1.types import ET0Input

# ---------------------------------------------------------------------------
# Tolerance — same as T1-01 tests
# ---------------------------------------------------------------------------
REL_TOL = 1e-9

# ---------------------------------------------------------------------------
# Golden fixture (read-only)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent.parent.parent
GOLDEN_PATH = REPO_ROOT.parent / "tests" / "fixtures" / "layer1_golden_test_cases.json"

with GOLDEN_PATH.open(encoding="utf-8") as _f:
    _GOLDEN_CASES: list[dict] = json.load(_f)

_GOLDEN: dict[str, dict] = {c["id"]: c for c in _GOLDEN_CASES}


# ===========================================================================
# Helpers
# ===========================================================================


def _et0_input_from_golden(case_id: str) -> ET0Input:
    """Build an ET0Input from a golden fixture entry."""
    inp = _GOLDEN[case_id]["inputs"]
    return ET0Input(
        T_c=inp["T_c"],
        RH_pct=inp["RH_pct"],
        wind_m_s=inp["wind_m_s"],
        Rn_MJ_m2_day=inp["Rn_MJ_m2_day"],
        elevation_m=inp["elevation_m"],
    )


# ===========================================================================
# calculate_et0 — low-level function
# ===========================================================================


class TestCalculateET0:
    """
    Tests for the core ET₀ calculation with explicit atmospheric inputs.

    Expected values are computed directly from the approved equation:
        ET₀ = [0.408·Δ·(Rn−G) + γ·(900/(T+273))·u2·(es−ea)]
              / [Δ + γ·(1+0.34·u2)]
    and compared to the golden fixture where available.
    """

    @pytest.mark.parametrize(
        "case_id",
        [
            "L1-GOLDEN-001",
            "L1-GOLDEN-002",
            "L1-GOLDEN-003",
            "L1-GOLDEN-004",
            "L1-GOLDEN-005",
        ],
    )
    def test_golden_et0_from_precomputed_atmospheric(self, case_id: str):
        """
        Verify ET₀ using pre-computed atmospheric values from the golden fixture.

        This exercises calculate_et0 in isolation (atmospheric inputs are taken
        directly from the fixture's expected values, not re-derived).
        """
        exp = _GOLDEN[case_id]["expected"]
        inp = _GOLDEN[case_id]["inputs"]

        result = calculate_et0(
            T_c=inp["T_c"],
            u2_m_s=inp["wind_m_s"],
            Rn_MJ_m2_day=inp["Rn_MJ_m2_day"],
            es_kpa=exp["es_kpa"],
            ea_kpa=exp["ea_kpa"],
            delta_kpa_per_c=exp["delta_kpa_per_c"],
            gamma_kpa_per_c=exp["gamma_kpa_per_c"],
            G_MJ_m2_day=0.0,
        )
        assert math.isclose(result, exp["et0_mm_day"], rel_tol=REL_TOL), (
            f"{case_id}: ET₀={result}, expected {exp['et0_mm_day']}"
        )

    def test_g_zero_convention(self):
        """
        With G explicitly passed as 0, the result must equal the G=0 default.

        The daily prototype convention requires G=0 (Layer 1 spec §3.2).
        """
        kwargs = dict(
            T_c=30.0,
            u2_m_s=2.0,
            Rn_MJ_m2_day=18.0,
            es_kpa=4.243065058759013,
            ea_kpa=2.1215325293795066,
            delta_kpa_per_c=0.24336253881311395,
            gamma_kpa_per_c=0.06058425950238184,
        )
        result_default = calculate_et0(**kwargs)  # G defaults to 0
        result_explicit = calculate_et0(**kwargs, G_MJ_m2_day=0.0)
        assert result_default == result_explicit

    def test_higher_rn_increases_et0(self):
        """
        Higher net radiation must produce higher ET₀, all else equal.

        This tests the monotonic response to increased evaporative demand.
        """
        base = dict(
            T_c=30.0,
            u2_m_s=2.0,
            es_kpa=4.24,
            ea_kpa=2.12,
            delta_kpa_per_c=0.243,
            gamma_kpa_per_c=0.0606,
        )
        low_rn = calculate_et0(Rn_MJ_m2_day=10.0, **base)
        high_rn = calculate_et0(Rn_MJ_m2_day=25.0, **base)
        assert high_rn > low_rn, "Higher Rn must produce higher ET₀"

    def test_higher_vpd_increases_et0(self):
        """Higher VPD (drier air) must produce higher ET₀."""
        base = dict(
            T_c=30.0,
            u2_m_s=2.0,
            Rn_MJ_m2_day=18.0,
            es_kpa=4.24,
            delta_kpa_per_c=0.243,
            gamma_kpa_per_c=0.0606,
        )
        low_vpd = calculate_et0(ea_kpa=3.5, **base)   # ea close to es
        high_vpd = calculate_et0(ea_kpa=1.0, **base)  # ea far below es
        assert high_vpd > low_vpd, "Higher VPD must produce higher ET₀"

    def test_higher_wind_increases_et0(self):
        """Higher wind speed must produce higher ET₀, given a positive VPD."""
        base = dict(
            T_c=30.0,
            Rn_MJ_m2_day=18.0,
            es_kpa=4.24,
            ea_kpa=2.12,
            delta_kpa_per_c=0.243,
            gamma_kpa_per_c=0.0606,
        )
        low_wind = calculate_et0(u2_m_s=0.5, **base)
        high_wind = calculate_et0(u2_m_s=5.0, **base)
        assert high_wind > low_wind, "Higher wind must produce higher ET₀"

    def test_deterministic(self):
        """Same inputs must always produce the same ET₀."""
        kwargs = dict(
            T_c=30.0,
            u2_m_s=2.0,
            Rn_MJ_m2_day=18.0,
            es_kpa=4.243065058759013,
            ea_kpa=2.1215325293795066,
            delta_kpa_per_c=0.24336253881311395,
            gamma_kpa_per_c=0.06058425950238184,
        )
        assert calculate_et0(**kwargs) == calculate_et0(**kwargs)


# ===========================================================================
# compute_et0 — high-level function integrating T1-01
# ===========================================================================


class TestComputeET0:
    """
    Tests for the high-level compute_et0 that accepts ET0Input and
    internally calls compute_atmospheric from T1-01.
    """

    @pytest.mark.parametrize(
        "case_id",
        [
            "L1-GOLDEN-001",
            "L1-GOLDEN-002",
            "L1-GOLDEN-003",
            "L1-GOLDEN-004",
            "L1-GOLDEN-005",
        ],
    )
    def test_golden_et0_end_to_end(self, case_id: str):
        """
        End-to-end golden test: ET0Input → compute_et0 → ET0Result.

        ET₀ must match the golden fixture expected value at rel_tol=1e-9.
        Atmospheric intermediates must also match (full traceability).
        """
        inp = _et0_input_from_golden(case_id)
        exp = _GOLDEN[case_id]["expected"]
        result: ET0Result = compute_et0(inp)

        assert math.isclose(result.et0_mm_day, exp["et0_mm_day"], rel_tol=REL_TOL), (
            f"{case_id}: ET₀={result.et0_mm_day}, expected {exp['et0_mm_day']}"
        )
        # Confirm atmospheric intermediates are also preserved correctly
        assert math.isclose(result.es_kpa, exp["es_kpa"], rel_tol=REL_TOL)
        assert math.isclose(result.ea_kpa, exp["ea_kpa"], rel_tol=REL_TOL)
        assert math.isclose(result.delta_kpa_per_c, exp["delta_kpa_per_c"], rel_tol=REL_TOL)
        assert math.isclose(result.pressure_kpa, exp["pressure_kpa"], rel_tol=REL_TOL)
        assert math.isclose(result.gamma_kpa_per_c, exp["gamma_kpa_per_c"], rel_tol=REL_TOL)

    def test_g_is_zero_in_result(self):
        """
        The daily prototype convention G=0 must be reflected in the result.

        Verifying this here ensures a future sub-daily extension doesn't
        silently drop a non-zero G.
        """
        inp = _et0_input_from_golden("L1-GOLDEN-001")
        result = compute_et0(inp)
        assert result.G_MJ_m2_day == 0.0

    def test_returns_et0_result_type(self):
        """compute_et0 must return an ET0Result instance."""
        inp = _et0_input_from_golden("L1-GOLDEN-001")
        result = compute_et0(inp)
        assert isinstance(result, ET0Result)

    def test_frozen_result_is_immutable(self):
        """ET0Result is a frozen dataclass — mutation must raise."""
        inp = _et0_input_from_golden("L1-GOLDEN-001")
        result = compute_et0(inp)
        with pytest.raises((AttributeError, TypeError)):
            result.et0_mm_day = 0.0  # type: ignore[misc]

    def test_deterministic_on_repeated_call(self):
        """Same ET0Input must always produce an identical ET0Result."""
        inp = _et0_input_from_golden("L1-GOLDEN-002")
        assert compute_et0(inp) == compute_et0(inp)

    def test_vpd_in_result_equals_es_minus_ea(self):
        """
        VPD stored in the result must be self-consistent with es and ea.

        VPD is computed by T1-01 and forwarded into ET0Result.
        This test guards against copy-paste errors in the forwarding code.
        """
        inp = _et0_input_from_golden("L1-GOLDEN-003")
        result = compute_et0(inp)
        assert math.isclose(
            result.vpd_kpa, result.es_kpa - result.ea_kpa, rel_tol=REL_TOL
        )

    def test_high_demand_scenario_produces_higher_et0(self):
        """
        A hot, dry, windy day (L1-GOLDEN-005) must yield more ET₀ than
        a mild, humid day (L1-GOLDEN-003).

        Validates the qualitative response to evaporative demand.
        """
        mild = compute_et0(_et0_input_from_golden("L1-GOLDEN-003"))
        extreme = compute_et0(_et0_input_from_golden("L1-GOLDEN-005"))
        assert extreme.et0_mm_day > mild.et0_mm_day, (
            f"High-demand ET₀ ({extreme.et0_mm_day:.4f}) should exceed "
            f"mild ET₀ ({mild.et0_mm_day:.4f})"
        )
