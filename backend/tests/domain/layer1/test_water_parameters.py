"""
T1-04 — Tests for root-zone soil water availability parameters.

Tests cover:
  - calculate_taw          (TAW = 1000 × (θ_FC − θ_WP) × Zr)
  - calculate_p            (p = clip(p_table + 0.04 × (5 − ETc), 0.1, 0.8))
  - calculate_raw          (RAW = p × TAW)
  - calculate_theta_critical (θ_critical = θ_FC − p × (θ_FC − θ_WP))
  - compute_water_parameters (full pipeline; composition with T1-03 ETc)

Golden test fixture ground truth:
  tests/fixtures/layer1_golden_test_cases.json  (read-only, never modified)

All five golden cases supply taw_mm, p, raw_mm, theta_critical_m3_m3.
L1-GOLDEN-005 explicitly exercises the lower-bound clipping (p=0.1).

Additional local calculation fixtures are used for isolated edge-case
coverage (upper-bound clipping, p>0.8 raw value, low ETc).  These are
labeled as calculation fixtures and are not crop-configuration defaults.

Source of truth: docs/05_LAYER1_SPEC.docx §3.4
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from app.domain.layer1.water_parameters import (
    WaterParametersResult,
    calculate_p,
    calculate_raw,
    calculate_taw,
    calculate_theta_critical,
    compute_water_parameters,
)
from app.domain.layer1.etc import compute_etc
from app.domain.layer1.et0 import compute_et0
from app.domain.layer1.types import ET0Input

# ---------------------------------------------------------------------------
# Tolerance
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


# ---------------------------------------------------------------------------
# Local calculation fixtures (not crop-configuration values)
# ---------------------------------------------------------------------------
# These are synthetic parameter sets used to isolate specific behaviors
# (upper-bound clipping, low-ETc response, etc.) not covered by the five
# golden cases.  They do NOT represent any real crop or field configuration.

# Calculation fixture A — triggers p upper-bound clipping (p_raw > 0.8)
# p_raw = 0.55 + 0.04 × (5 - 0.5) = 0.55 + 0.18 = 0.73 — NOT clipped, adjust
# p_raw = 0.70 + 0.04 × (5 - 0.0) = 0.70 + 0.20 = 0.90 > 0.8 → clipped to 0.8
_CALC_FIXTURE_UPPER_CLIP = {
    "p_table": 0.70,  # calc fixture only — not a named crop value
    "ETc_mm_day": 0.0,
    # p_raw = 0.70 + 0.04 × 5 = 0.90 → clipped to 0.8
    "expected_p": 0.8,
}

# Calculation fixture B — ETc exactly 5 mm/day → correction term is 0
_CALC_FIXTURE_ETc5 = {
    "p_table": 0.50,  # calc fixture only
    "ETc_mm_day": 5.0,
    "expected_p": 0.50,
}

# Calculation fixture C — generic soil params for isolated TAW/RAW/theta_crit tests
# Not a named crop or soil classification.
_CALC_FIXTURE_SOIL = {
    "theta_FC": 0.35,   # calc fixture only
    "theta_WP": 0.15,   # calc fixture only
    "Zr_m": 0.8,
    # TAW = 1000 × (0.35 - 0.15) × 0.8 = 160.0 mm
    "expected_TAW_mm": 160.0,
}


# ===========================================================================
# calculate_taw — TAW = 1000 × (θ_FC − θ_WP) × Zr
# ===========================================================================


class TestCalculateTAW:
    """Tests for the total available water calculation."""

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_golden_taw(self, case_id: str):
        """TAW must match the golden fixture expected value at rel_tol=1e-9."""
        inp = _GOLDEN[case_id]["inputs"]
        exp = _GOLDEN[case_id]["expected"]
        result = calculate_taw(
            theta_FC=inp["theta_FC"],
            theta_WP=inp["theta_WP"],
            Zr_m=inp["root_depth_m"],
        )
        assert math.isclose(result, exp["taw_mm"], rel_tol=REL_TOL), (
            f"{case_id}: TAW={result}, expected {exp['taw_mm']}"
        )

    def test_calc_fixture_taw(self):
        """Calc-fixture soil params produce the expected TAW."""
        f = _CALC_FIXTURE_SOIL
        result = calculate_taw(f["theta_FC"], f["theta_WP"], f["Zr_m"])
        assert math.isclose(result, f["expected_TAW_mm"], rel_tol=REL_TOL)

    def test_taw_unit_conversion(self):
        """
        TAW must express depth in mm, not m.

        1000 × (0.2 − 0.1) × 1.0 = 100 mm (not 0.1 m).
        """
        result = calculate_taw(theta_FC=0.2, theta_WP=0.1, Zr_m=1.0)
        assert math.isclose(result, 100.0, rel_tol=REL_TOL)

    def test_taw_scales_with_depth(self):
        """Doubling Zr must double TAW, all else equal."""
        shallow = calculate_taw(0.3, 0.15, 0.5)
        deep = calculate_taw(0.3, 0.15, 1.0)
        assert math.isclose(deep, 2 * shallow, rel_tol=REL_TOL)

    def test_taw_scales_with_water_holding_capacity(self):
        """Larger (θ_FC − θ_WP) must give larger TAW."""
        low_whc = calculate_taw(0.25, 0.15, 0.6)   # whc = 0.10
        high_whc = calculate_taw(0.35, 0.15, 0.6)  # whc = 0.20
        assert high_whc > low_whc

    def test_deterministic(self):
        assert calculate_taw(0.3, 0.15, 0.6) == calculate_taw(0.3, 0.15, 0.6)


# ===========================================================================
# calculate_p — p = clip(p_table + 0.04 × (5 − ETc), 0.1, 0.8)
# ===========================================================================


class TestCalculateP:
    """Tests for the ETc-adjusted depletion fraction."""

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_golden_p(self, case_id: str):
        """p must match the golden fixture expected value at rel_tol=1e-9."""
        inp = _GOLDEN[case_id]["inputs"]
        exp = _GOLDEN[case_id]["expected"]
        result = calculate_p(
            p_table=inp["p_table"],
            ETc_mm_day=exp["etc_mm_day"],
        )
        assert math.isclose(result, exp["p"], rel_tol=REL_TOL), (
            f"{case_id}: p={result}, expected {exp['p']}"
        )

    def test_lower_bound_clipping(self):
        """
        Very high ETc must clip p to the lower bound 0.1.

        L1-GOLDEN-005 covers this via the fixture; this test uses a
        calculation fixture to verify the clip mechanism directly.
        ETc=100 → p_raw = 0.55 + 0.04 × (5 - 100) = 0.55 - 3.8 = -3.25 → clipped to 0.1
        """
        result = calculate_p(p_table=0.55, ETc_mm_day=100.0)
        assert result == 0.1

    def test_golden_005_lower_clip(self):
        """L1-GOLDEN-005 explicitly tests lower-bound clipping at p=0.10."""
        inp = _GOLDEN["L1-GOLDEN-005"]["inputs"]
        exp = _GOLDEN["L1-GOLDEN-005"]["expected"]
        result = calculate_p(p_table=inp["p_table"], ETc_mm_day=exp["etc_mm_day"])
        assert result == 0.1
        assert exp["p"] == 0.1

    def test_upper_bound_clipping(self):
        """
        Very low ETc must clip p to the upper bound 0.8.

        Calculation fixture: p_table=0.70, ETc=0 → p_raw=0.90 → clipped to 0.8.
        """
        f = _CALC_FIXTURE_UPPER_CLIP
        result = calculate_p(p_table=f["p_table"], ETc_mm_day=f["ETc_mm_day"])
        assert result == f["expected_p"]

    def test_etcfive_gives_no_correction(self):
        """ETc = 5 mm/day makes the correction term 0; p must equal p_table exactly."""
        f = _CALC_FIXTURE_ETc5
        result = calculate_p(p_table=f["p_table"], ETc_mm_day=f["ETc_mm_day"])
        assert math.isclose(result, f["expected_p"], rel_tol=REL_TOL)

    def test_high_etc_reduces_p(self):
        """Higher ETc must produce a lower adjusted p (increased moisture sensitivity)."""
        p_low_etc = calculate_p(p_table=0.55, ETc_mm_day=2.0)
        p_high_etc = calculate_p(p_table=0.55, ETc_mm_day=10.0)
        assert p_high_etc < p_low_etc

    def test_low_etc_raises_p(self):
        """Lower ETc must produce a higher adjusted p (reduced moisture sensitivity)."""
        p_very_low = calculate_p(p_table=0.50, ETc_mm_day=1.0)
        p_moderate = calculate_p(p_table=0.50, ETc_mm_day=5.0)
        assert p_very_low > p_moderate

    def test_p_always_in_bounds(self):
        """p must always lie in [0.1, 0.8] regardless of input values."""
        for ETc in [-10.0, 0.0, 5.0, 15.0, 100.0]:
            result = calculate_p(p_table=0.55, ETc_mm_day=ETc)
            assert 0.1 <= result <= 0.8, f"p={result} out of bounds at ETc={ETc}"

    def test_deterministic(self):
        assert calculate_p(0.55, 7.39) == calculate_p(0.55, 7.39)


# ===========================================================================
# calculate_raw — RAW = p × TAW
# ===========================================================================


class TestCalculateRAW:
    """Tests for readily available water."""

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_golden_raw(self, case_id: str):
        """RAW must match the golden fixture expected value at rel_tol=1e-9."""
        exp = _GOLDEN[case_id]["expected"]
        result = calculate_raw(p=exp["p"], TAW_mm=exp["taw_mm"])
        assert math.isclose(result, exp["raw_mm"], rel_tol=REL_TOL), (
            f"{case_id}: RAW={result}, expected {exp['raw_mm']}"
        )

    def test_raw_equals_p_times_taw(self):
        """RAW must equal p × TAW exactly."""
        p = 0.45
        taw = 90.0
        assert math.isclose(calculate_raw(p, taw), p * taw, rel_tol=REL_TOL)

    def test_raw_never_exceeds_taw(self):
        """RAW ≤ TAW for any valid p in [0.1, 0.8]."""
        taw = 90.0
        for p in [0.1, 0.4, 0.8]:
            assert calculate_raw(p, taw) <= taw

    def test_higher_p_gives_higher_raw(self):
        """Higher p must give higher RAW for the same TAW."""
        taw = 90.0
        assert calculate_raw(0.3, taw) < calculate_raw(0.6, taw)

    def test_deterministic(self):
        assert calculate_raw(0.45, 90.0) == calculate_raw(0.45, 90.0)


# ===========================================================================
# calculate_theta_critical — θ_critical = θ_FC − p × (θ_FC − θ_WP)
# ===========================================================================


class TestCalculateThetaCritical:
    """Tests for the critical soil-moisture threshold."""

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_golden_theta_critical(self, case_id: str):
        """θ_critical must match the golden fixture value at rel_tol=1e-9."""
        inp = _GOLDEN[case_id]["inputs"]
        exp = _GOLDEN[case_id]["expected"]
        result = calculate_theta_critical(
            theta_FC=inp["theta_FC"],
            p=exp["p"],
            theta_WP=inp["theta_WP"],
        )
        assert math.isclose(result, exp["theta_critical_m3_m3"], rel_tol=REL_TOL), (
            f"{case_id}: θ_crit={result}, expected {exp['theta_critical_m3_m3']}"
        )

    def test_theta_critical_at_p_zero_equals_theta_fc(self):
        """
        When p=0, θ_critical = θ_FC (depletion never allowed; conceptual edge case).

        This is outside the spec-allowed range [0.1, 0.8] but validates the
        equation algebraically: θ_FC − 0 × (θ_FC − θ_WP) = θ_FC.
        """
        result = calculate_theta_critical(theta_FC=0.3, p=0.0, theta_WP=0.15)
        assert math.isclose(result, 0.3, rel_tol=REL_TOL)

    def test_theta_critical_at_p_one_equals_theta_wp(self):
        """
        When p=1, θ_critical = θ_WP (all available water allowed; conceptual edge case).

        θ_FC − 1 × (θ_FC − θ_WP) = θ_WP.
        """
        result = calculate_theta_critical(theta_FC=0.3, p=1.0, theta_WP=0.15)
        assert math.isclose(result, 0.15, rel_tol=REL_TOL)

    def test_theta_critical_between_wp_and_fc(self):
        """θ_critical must always lie between θ_WP and θ_FC for valid p in [0.1, 0.8]."""
        theta_FC = 0.3
        theta_WP = 0.15
        for p in [0.1, 0.4, 0.8]:
            crit = calculate_theta_critical(theta_FC, p, theta_WP)
            assert theta_WP <= crit <= theta_FC, (
                f"θ_crit={crit} not between θ_WP={theta_WP} and θ_FC={theta_FC} at p={p}"
            )

    def test_higher_p_gives_lower_theta_critical(self):
        """Higher p (larger depletion fraction) must lower θ_critical."""
        crit_low_p = calculate_theta_critical(0.3, 0.2, 0.15)
        crit_high_p = calculate_theta_critical(0.3, 0.6, 0.15)
        assert crit_low_p > crit_high_p

    def test_deterministic(self):
        assert (
            calculate_theta_critical(0.3, 0.454, 0.15)
            == calculate_theta_critical(0.3, 0.454, 0.15)
        )


# ===========================================================================
# compute_water_parameters — full pipeline
# ===========================================================================


class TestComputeWaterParameters:
    """
    Tests for the high-level compute_water_parameters that composes all four
    sub-calculations in a single call.
    """

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_golden_all_fields(self, case_id: str):
        """
        Full-pipeline golden test: all four output fields must match the
        fixture expected values at rel_tol=1e-9.
        """
        inp = _GOLDEN[case_id]["inputs"]
        exp = _GOLDEN[case_id]["expected"]
        result: WaterParametersResult = compute_water_parameters(
            theta_FC=inp["theta_FC"],
            theta_WP=inp["theta_WP"],
            Zr_m=inp["root_depth_m"],
            p_table=inp["p_table"],
            ETc_mm_day=exp["etc_mm_day"],  # use the pre-computed ETc from fixture
        )
        assert math.isclose(result.TAW_mm, exp["taw_mm"], rel_tol=REL_TOL), (
            f"{case_id}: TAW={result.TAW_mm}"
        )
        assert math.isclose(result.p, exp["p"], rel_tol=REL_TOL), (
            f"{case_id}: p={result.p}"
        )
        assert math.isclose(result.RAW_mm, exp["raw_mm"], rel_tol=REL_TOL), (
            f"{case_id}: RAW={result.RAW_mm}"
        )
        assert math.isclose(
            result.theta_critical, exp["theta_critical_m3_m3"], rel_tol=REL_TOL
        ), f"{case_id}: θ_crit={result.theta_critical}"

    def test_input_echo_fields(self):
        """WaterParametersResult must echo all five input values for traceability."""
        inp = _GOLDEN["L1-GOLDEN-001"]["inputs"]
        exp = _GOLDEN["L1-GOLDEN-001"]["expected"]
        result = compute_water_parameters(
            theta_FC=inp["theta_FC"],
            theta_WP=inp["theta_WP"],
            Zr_m=inp["root_depth_m"],
            p_table=inp["p_table"],
            ETc_mm_day=exp["etc_mm_day"],
        )
        assert result.theta_FC == inp["theta_FC"]
        assert result.theta_WP == inp["theta_WP"]
        assert result.Zr_m == inp["root_depth_m"]
        assert result.p_table == inp["p_table"]
        assert result.ETc_mm_day == exp["etc_mm_day"]

    def test_returns_water_parameters_result_type(self):
        """compute_water_parameters must return a WaterParametersResult instance."""
        inp = _GOLDEN["L1-GOLDEN-001"]["inputs"]
        exp = _GOLDEN["L1-GOLDEN-001"]["expected"]
        result = compute_water_parameters(
            theta_FC=inp["theta_FC"],
            theta_WP=inp["theta_WP"],
            Zr_m=inp["root_depth_m"],
            p_table=inp["p_table"],
            ETc_mm_day=exp["etc_mm_day"],
        )
        assert isinstance(result, WaterParametersResult)

    def test_frozen_result_is_immutable(self):
        """WaterParametersResult is frozen — mutation must raise."""
        inp = _GOLDEN["L1-GOLDEN-001"]["inputs"]
        exp = _GOLDEN["L1-GOLDEN-001"]["expected"]
        result = compute_water_parameters(
            theta_FC=inp["theta_FC"],
            theta_WP=inp["theta_WP"],
            Zr_m=inp["root_depth_m"],
            p_table=inp["p_table"],
            ETc_mm_day=exp["etc_mm_day"],
        )
        with pytest.raises((AttributeError, TypeError)):
            result.TAW_mm = 0.0  # type: ignore[misc]

    def test_deterministic_on_repeated_call(self):
        """Same inputs must always produce an identical WaterParametersResult."""
        inp = _GOLDEN["L1-GOLDEN-003"]["inputs"]
        exp = _GOLDEN["L1-GOLDEN-003"]["expected"]
        kwargs = dict(
            theta_FC=inp["theta_FC"],
            theta_WP=inp["theta_WP"],
            Zr_m=inp["root_depth_m"],
            p_table=inp["p_table"],
            ETc_mm_day=exp["etc_mm_day"],
        )
        assert compute_water_parameters(**kwargs) == compute_water_parameters(**kwargs)

    def test_composition_with_t103_etc(self):
        """
        Validate that compute_water_parameters composes cleanly with T1-02/T1-03:
        ET0Input → compute_et0 → compute_etc → compute_water_parameters.

        Uses L1-GOLDEN-001 to verify the chain produces the approved output.
        """
        inp = _GOLDEN["L1-GOLDEN-001"]["inputs"]
        exp = _GOLDEN["L1-GOLDEN-001"]["expected"]

        # T1-02 — ET₀
        et0_result = compute_et0(
            ET0Input(
                T_c=inp["T_c"],
                RH_pct=inp["RH_pct"],
                wind_m_s=inp["wind_m_s"],
                Rn_MJ_m2_day=inp["Rn_MJ_m2_day"],
                elevation_m=inp["elevation_m"],
            )
        )
        # T1-03 — ETc
        etc_result = compute_etc(Kc=inp["Kc"], et0_result=et0_result)

        # T1-04 — water parameters
        wp_result = compute_water_parameters(
            theta_FC=inp["theta_FC"],
            theta_WP=inp["theta_WP"],
            Zr_m=inp["root_depth_m"],
            p_table=inp["p_table"],
            ETc_mm_day=etc_result.etc_mm_day,
        )

        assert math.isclose(wp_result.TAW_mm, exp["taw_mm"], rel_tol=REL_TOL)
        assert math.isclose(wp_result.p, exp["p"], rel_tol=REL_TOL)
        assert math.isclose(wp_result.RAW_mm, exp["raw_mm"], rel_tol=REL_TOL)
        assert math.isclose(
            wp_result.theta_critical, exp["theta_critical_m3_m3"], rel_tol=REL_TOL
        )
