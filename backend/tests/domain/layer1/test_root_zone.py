"""
T1-05 — Tests for root-zone soil state and irrigation prescription.

Tests cover:
  - calculate_depletion      (Dr from θ_current, clamping)
  - check_irrigation_trigger (Dr >= RAW, equality boundary)
  - calculate_net_irrigation (I_net full-refill or zero)
  - calculate_gross_irrigation (I_gross = I_net / Ea)
  - calculate_water_volume   (V = I_gross × area)
  - calculate_valve_runtime  (t = V / flow)
  - compute_root_zone        (full pipeline, composition with T1-04)

Golden fixture ground truth (read-only):
  tests/fixtures/layer1_golden_test_cases.json
  → depletion_mm, irrigation_trigger, net_irrigation_mm, gross_irrigation_mm
    for all 5 cases.

The golden fixture does NOT contain field_area_m2, flow_l_per_min, or
valve_runtime_minutes.  Those are tested with explicit local calculation
fixtures, labeled as such.

Source of truth: docs/05_LAYER1_SPEC.docx §3.5, §3.6, §3.8
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from app.domain.layer1.root_zone import (
    RootZoneResult,
    calculate_depletion,
    calculate_gross_irrigation,
    calculate_net_irrigation,
    calculate_valve_runtime,
    calculate_water_volume,
    check_irrigation_trigger,
    compute_root_zone,
)
from app.domain.layer1.water_parameters import compute_water_parameters
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
# Local calculation fixtures
# (not crop/soil configuration values; used for volume/runtime and edge cases)
# ---------------------------------------------------------------------------

# Calc fixture: field area and flow for volume/runtime tests
_CALC_AREA_M2 = 500.0        # m² — calculation fixture only
_CALC_FLOW_L_MIN = 120.0     # L/min — calculation fixture only
_CALC_EFF = 0.9              # application efficiency — matches golden fixture


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _golden_inputs(case_id: str) -> dict:
    return _GOLDEN[case_id]["inputs"]


def _golden_expected(case_id: str) -> dict:
    return _GOLDEN[case_id]["expected"]


def _compute_root_zone_from_golden(case_id: str) -> RootZoneResult:
    """Build a full RootZoneResult from a golden case using its pre-computed RAW/TAW."""
    inp = _golden_inputs(case_id)
    exp = _golden_expected(case_id)
    return compute_root_zone(
        theta_current=inp["theta_current"],
        theta_FC=inp["theta_FC"],
        theta_WP=inp["theta_WP"],
        Zr_m=inp["root_depth_m"],
        TAW_mm=exp["taw_mm"],
        RAW_mm=exp["raw_mm"],
        application_efficiency=inp["application_efficiency"],
        field_area_m2=_CALC_AREA_M2,
        flow_l_per_min=_CALC_FLOW_L_MIN,
    )


# ===========================================================================
# calculate_depletion — Dr = clip(1000 × (θ_FC − θ) × Zr, 0, TAW)
# ===========================================================================


class TestCalculateDepletion:
    """Tests for root-zone depletion calculation and clamping."""

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_golden_depletion(self, case_id: str):
        """Dr must match the golden fixture depletion_mm at rel_tol=1e-9."""
        inp = _golden_inputs(case_id)
        exp = _golden_expected(case_id)
        result = calculate_depletion(
            theta_current=inp["theta_current"],
            theta_FC=inp["theta_FC"],
            Zr_m=inp["root_depth_m"],
            TAW_mm=exp["taw_mm"],
        )
        assert math.isclose(result, exp["depletion_mm"], rel_tol=REL_TOL), (
            f"{case_id}: Dr={result}, expected {exp['depletion_mm']}"
        )

    def test_theta_above_fc_clamps_to_zero(self):
        """θ_current > θ_FC → Dr must be 0 (soil above field capacity)."""
        dr = calculate_depletion(
            theta_current=0.35,   # above θ_FC=0.3
            theta_FC=0.3,
            Zr_m=0.6,
            TAW_mm=90.0,
        )
        assert dr == 0.0

    def test_theta_exactly_at_fc_gives_zero_depletion(self):
        """θ_current == θ_FC → Dr must be exactly 0."""
        dr = calculate_depletion(
            theta_current=0.3,
            theta_FC=0.3,
            Zr_m=0.6,
            TAW_mm=90.0,
        )
        assert dr == 0.0

    def test_theta_at_wp_clamps_to_taw(self):
        """θ_current == θ_WP → Dr must equal TAW (soil at wilting point).

        The TAW already encodes the WP boundary:
        TAW = 1000 × (θ_FC − θ_WP) × Zr = 1000 × (0.3 − 0.15) × 0.6 = 90.0 mm
        Dr_raw = 1000 × (0.3 − 0.15) × 0.6 = 90.0 mm → clipped to TAW = 90.0 mm
        """
        dr = calculate_depletion(
            theta_current=0.15,   # == θ_WP
            theta_FC=0.3,
            Zr_m=0.6,
            TAW_mm=90.0,
        )
        assert math.isclose(dr, 90.0, rel_tol=REL_TOL)

    def test_theta_below_wp_clamps_to_taw(self):
        """θ_current < θ_WP → Dr must be clipped to TAW."""
        dr = calculate_depletion(
            theta_current=0.05,   # well below θ_WP
            theta_FC=0.3,
            Zr_m=0.6,
            TAW_mm=90.0,
        )
        assert math.isclose(dr, 90.0, rel_tol=REL_TOL)

    def test_depletion_never_negative(self):
        """Dr must never be negative regardless of how wet the soil is."""
        for theta in [0.31, 0.40, 0.50]:
            dr = calculate_depletion(theta, theta_FC=0.3, Zr_m=0.6, TAW_mm=90.0)
            assert dr >= 0.0, f"Negative Dr={dr} at θ_current={theta}"

    def test_depletion_never_exceeds_taw(self):
        """Dr must never exceed TAW regardless of how dry the soil is."""
        for theta in [0.15, 0.10, 0.0]:
            dr = calculate_depletion(theta, theta_FC=0.3, Zr_m=0.6, TAW_mm=90.0)
            assert dr <= 90.0, f"Dr={dr} exceeds TAW=90 at θ_current={theta}"

    def test_depletion_scales_with_depth(self):
        """Doubling Zr must double Dr, all else equal."""
        dr_shallow = calculate_depletion(0.24, 0.3, 0.5, 75.0)
        dr_deep = calculate_depletion(0.24, 0.3, 1.0, 150.0)
        assert math.isclose(dr_deep, 2 * dr_shallow, rel_tol=REL_TOL)

    def test_deterministic(self):
        assert calculate_depletion(0.24, 0.3, 0.6, 90.0) == calculate_depletion(
            0.24, 0.3, 0.6, 90.0
        )


# ===========================================================================
# check_irrigation_trigger — Dr >= RAW
# ===========================================================================


class TestCheckIrrigationTrigger:
    """Tests for the trigger decision."""

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_golden_trigger(self, case_id: str):
        """Trigger must match the golden fixture boolean value."""
        exp = _golden_expected(case_id)
        result = check_irrigation_trigger(
            Dr_mm=exp["depletion_mm"],
            RAW_mm=exp["raw_mm"],
        )
        assert result == exp["irrigation_trigger"], (
            f"{case_id}: trigger={result}, expected {exp['irrigation_trigger']}"
        )

    def test_dr_less_than_raw_no_trigger(self):
        """Dr < RAW → no trigger."""
        assert check_irrigation_trigger(Dr_mm=30.0, RAW_mm=40.0) is False

    def test_dr_equal_raw_triggers(self):
        """Dr == RAW → trigger (equality boundary must trigger, §3.6)."""
        assert check_irrigation_trigger(Dr_mm=40.0, RAW_mm=40.0) is True

    def test_dr_greater_than_raw_triggers(self):
        """Dr > RAW → trigger."""
        assert check_irrigation_trigger(Dr_mm=50.0, RAW_mm=40.0) is True

    def test_golden_004_boundary_case(self):
        """
        L1-GOLDEN-004 is the explicit boundary test: Dr == RAW → trigger=True.

        The fixture was constructed so that θ_current == θ_critical, making
        Dr exactly equal to RAW.  The trigger must be True.
        """
        exp = _golden_expected("L1-GOLDEN-004")
        # Verify the fixture itself encodes a boundary case
        assert math.isclose(exp["depletion_mm"], exp["raw_mm"], rel_tol=1e-6)
        assert exp["irrigation_trigger"] is True

    def test_deterministic(self):
        assert check_irrigation_trigger(40.0, 40.0) == check_irrigation_trigger(40.0, 40.0)


# ===========================================================================
# calculate_net_irrigation
# ===========================================================================


class TestCalculateNetIrrigation:
    """Tests for net irrigation depth."""

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_golden_net_irrigation(self, case_id: str):
        """I_net must match the golden fixture net_irrigation_mm value."""
        exp = _golden_expected(case_id)
        result = calculate_net_irrigation(
            Dr_mm=exp["depletion_mm"],
            triggered=exp["irrigation_trigger"],
        )
        assert math.isclose(result, exp["net_irrigation_mm"], rel_tol=REL_TOL), (
            f"{case_id}: I_net={result}, expected {exp['net_irrigation_mm']}"
        )

    def test_net_zero_when_not_triggered(self):
        """I_net must be 0 when no irrigation is triggered."""
        assert calculate_net_irrigation(Dr_mm=30.0, triggered=False) == 0.0

    def test_net_equals_dr_when_triggered(self):
        """I_net must equal Dr when triggered (full-refill, §3.8)."""
        assert calculate_net_irrigation(Dr_mm=55.0, triggered=True) == 55.0

    def test_deterministic(self):
        assert calculate_net_irrigation(55.0, True) == calculate_net_irrigation(55.0, True)


# ===========================================================================
# calculate_gross_irrigation
# ===========================================================================


class TestCalculateGrossIrrigation:
    """Tests for gross irrigation depth."""

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-002", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_golden_gross_irrigation(self, case_id: str):
        """I_gross must match the golden fixture gross_irrigation_mm value."""
        exp = _golden_expected(case_id)
        inp = _golden_inputs(case_id)
        result = calculate_gross_irrigation(
            I_net_mm=exp["net_irrigation_mm"],
            application_efficiency=inp["application_efficiency"],
        )
        assert math.isclose(result, exp["gross_irrigation_mm"], rel_tol=REL_TOL), (
            f"{case_id}: I_gross={result}, expected {exp['gross_irrigation_mm']}"
        )

    def test_efficiency_one_gives_same_as_net(self):
        """E_a = 1.0 → I_gross == I_net (no losses)."""
        assert calculate_gross_irrigation(60.0, 1.0) == 60.0

    def test_gross_exceeds_net_for_efficiency_less_than_one(self):
        """I_gross > I_net for any E_a in (0, 1)."""
        net = 50.0
        gross = calculate_gross_irrigation(net, 0.8)
        assert gross > net

    def test_zero_efficiency_raises(self):
        """E_a = 0 is physically invalid and must raise ValueError."""
        with pytest.raises(ValueError, match="application_efficiency must be positive"):
            calculate_gross_irrigation(50.0, 0.0)

    def test_negative_efficiency_raises(self):
        """Negative E_a is physically invalid and must raise ValueError."""
        with pytest.raises(ValueError, match="application_efficiency must be positive"):
            calculate_gross_irrigation(50.0, -0.5)

    def test_deterministic(self):
        assert calculate_gross_irrigation(72.0, 0.9) == calculate_gross_irrigation(72.0, 0.9)


# ===========================================================================
# calculate_water_volume
# ===========================================================================


class TestCalculateWaterVolume:
    """Tests for water volume conversion (1 mm × 1 m² = 1 litre)."""

    def test_unit_relationship_one_mm_one_m2(self):
        """1 mm depth over 1 m² = 1 litre exactly."""
        assert calculate_water_volume(I_gross_mm=1.0, field_area_m2=1.0) == 1.0

    def test_unit_relationship_scale(self):
        """80 mm over 500 m² = 40 000 litres."""
        result = calculate_water_volume(80.0, 500.0)
        assert math.isclose(result, 40_000.0, rel_tol=REL_TOL)

    def test_zero_gross_gives_zero_volume(self):
        """No irrigation → zero volume."""
        assert calculate_water_volume(0.0, 500.0) == 0.0

    def test_volume_scales_with_area(self):
        """Doubling area must double volume."""
        v1 = calculate_water_volume(50.0, 200.0)
        v2 = calculate_water_volume(50.0, 400.0)
        assert math.isclose(v2, 2 * v1, rel_tol=REL_TOL)

    def test_volume_scales_with_gross_depth(self):
        """Doubling I_gross must double volume."""
        v1 = calculate_water_volume(30.0, 300.0)
        v2 = calculate_water_volume(60.0, 300.0)
        assert math.isclose(v2, 2 * v1, rel_tol=REL_TOL)

    def test_deterministic(self):
        assert calculate_water_volume(80.0, 500.0) == calculate_water_volume(80.0, 500.0)


# ===========================================================================
# calculate_valve_runtime
# ===========================================================================


class TestCalculateValveRuntime:
    """Tests for valve runtime calculation."""

    def test_runtime_equals_volume_over_flow(self):
        """t_valve = V / Q — basic formula verification."""
        # 6000 L / 120 L/min = 50 min
        result = calculate_valve_runtime(6_000.0, 120.0)
        assert math.isclose(result, 50.0, rel_tol=REL_TOL)

    def test_runtime_zero_volume_gives_zero(self):
        """Zero volume (no irrigation) → zero runtime."""
        result = calculate_valve_runtime(0.0, 120.0)
        assert result == 0.0

    def test_zero_flow_raises(self):
        """Flow = 0 is invalid (§3.8 requires valid positive flow)."""
        with pytest.raises(ValueError, match="flow_l_per_min must be positive"):
            calculate_valve_runtime(6_000.0, 0.0)

    def test_negative_flow_raises(self):
        """Negative flow is physically invalid."""
        with pytest.raises(ValueError, match="flow_l_per_min must be positive"):
            calculate_valve_runtime(6_000.0, -50.0)

    def test_higher_flow_gives_shorter_runtime(self):
        """Higher flow rate must produce shorter runtime for the same volume."""
        slow = calculate_valve_runtime(10_000.0, 100.0)
        fast = calculate_valve_runtime(10_000.0, 200.0)
        assert fast < slow

    def test_deterministic(self):
        assert calculate_valve_runtime(6_000.0, 120.0) == calculate_valve_runtime(
            6_000.0, 120.0
        )


# ===========================================================================
# compute_root_zone — full pipeline
# ===========================================================================


class TestComputeRootZone:
    """Tests for the high-level compute_root_zone pipeline."""

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_golden_depletion_and_trigger(self, case_id: str):
        """
        Full-pipeline golden test: Dr and irrigation_trigger must match fixture.

        Volume/runtime fields are not in the golden fixture; they are tested
        separately with local calculation fixtures.
        """
        exp = _golden_expected(case_id)
        result = _compute_root_zone_from_golden(case_id)
        assert math.isclose(result.Dr_mm, exp["depletion_mm"], rel_tol=REL_TOL), (
            f"{case_id}: Dr={result.Dr_mm}"
        )
        assert result.irrigation_trigger == exp["irrigation_trigger"], (
            f"{case_id}: trigger={result.irrigation_trigger}"
        )

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_golden_net_and_gross_irrigation(self, case_id: str):
        """I_net and I_gross must match golden fixture values."""
        exp = _golden_expected(case_id)
        result = _compute_root_zone_from_golden(case_id)
        assert math.isclose(result.I_net_mm, exp["net_irrigation_mm"], rel_tol=REL_TOL), (
            f"{case_id}: I_net={result.I_net_mm}"
        )
        assert math.isclose(result.I_gross_mm, exp["gross_irrigation_mm"], rel_tol=REL_TOL), (
            f"{case_id}: I_gross={result.I_gross_mm}"
        )

    def test_no_irrigation_prescription_when_no_trigger(self):
        """When not triggered, all prescription fields must be exactly 0."""
        result = _compute_root_zone_from_golden("L1-GOLDEN-001")  # no trigger
        assert result.irrigation_trigger is False
        assert result.I_net_mm == 0.0
        assert result.I_gross_mm == 0.0
        assert result.water_volume_litres == 0.0
        assert result.valve_runtime_minutes == 0.0

    def test_volume_and_runtime_when_triggered(self):
        """
        Volume and runtime must be computed correctly when irrigation is triggered.

        Uses L1-GOLDEN-002 (trigger=True) with local calc fixtures for area/flow.
        Expected:
          I_gross = 80.0 mm (from fixture)
          V = 80.0 mm × 500.0 m² = 40 000 litres
          t_valve = 40 000 L / 120.0 L/min = 333.333... min
        """
        result = _compute_root_zone_from_golden("L1-GOLDEN-002")
        assert result.irrigation_trigger is True
        expected_volume = result.I_gross_mm * _CALC_AREA_M2
        expected_runtime = expected_volume / _CALC_FLOW_L_MIN
        assert math.isclose(result.water_volume_litres, expected_volume, rel_tol=REL_TOL)
        assert math.isclose(result.valve_runtime_minutes, expected_runtime, rel_tol=REL_TOL)

    def test_traceability_echo_fields(self):
        """Result must echo TAW, RAW, θ_FC, θ_WP, Zr, θ_current, Ea, area, flow."""
        inp = _golden_inputs("L1-GOLDEN-001")
        exp = _golden_expected("L1-GOLDEN-001")
        result = _compute_root_zone_from_golden("L1-GOLDEN-001")
        assert result.theta_current == inp["theta_current"]
        assert result.theta_FC == inp["theta_FC"]
        assert result.theta_WP == inp["theta_WP"]
        assert result.Zr_m == inp["root_depth_m"]
        assert math.isclose(result.TAW_mm, exp["taw_mm"], rel_tol=REL_TOL)
        assert math.isclose(result.RAW_mm, exp["raw_mm"], rel_tol=REL_TOL)
        assert result.application_efficiency == inp["application_efficiency"]
        assert result.field_area_m2 == _CALC_AREA_M2
        assert result.flow_l_per_min == _CALC_FLOW_L_MIN

    def test_returns_root_zone_result_type(self):
        """compute_root_zone must return a RootZoneResult instance."""
        assert isinstance(_compute_root_zone_from_golden("L1-GOLDEN-001"), RootZoneResult)

    def test_frozen_result_is_immutable(self):
        """RootZoneResult is frozen — mutation must raise."""
        result = _compute_root_zone_from_golden("L1-GOLDEN-001")
        with pytest.raises((AttributeError, TypeError)):
            result.Dr_mm = 0.0  # type: ignore[misc]

    def test_deterministic_on_repeated_call(self):
        """Same inputs must produce identical RootZoneResult."""
        assert (
            _compute_root_zone_from_golden("L1-GOLDEN-003")
            == _compute_root_zone_from_golden("L1-GOLDEN-003")
        )

    def test_invalid_efficiency_raises_only_when_triggered(self):
        """
        Invalid efficiency must raise ValueError ONLY when irrigation is triggered.

        When no trigger, the prescription is not computed; the invalid value
        is stored but not used.
        """
        inp_no_trigger = _golden_inputs("L1-GOLDEN-001")  # trigger=False
        exp_no_trigger = _golden_expected("L1-GOLDEN-001")

        # Should NOT raise even with efficiency=0 — no trigger, no prescription
        result = compute_root_zone(
            theta_current=inp_no_trigger["theta_current"],
            theta_FC=inp_no_trigger["theta_FC"],
            theta_WP=inp_no_trigger["theta_WP"],
            Zr_m=inp_no_trigger["root_depth_m"],
            TAW_mm=exp_no_trigger["taw_mm"],
            RAW_mm=exp_no_trigger["raw_mm"],
            application_efficiency=0.0,   # invalid, but not used
            field_area_m2=500.0,
            flow_l_per_min=120.0,
        )
        assert result.irrigation_trigger is False

        # MUST raise when trigger fires with invalid efficiency
        inp_trigger = _golden_inputs("L1-GOLDEN-002")
        exp_trigger = _golden_expected("L1-GOLDEN-002")
        with pytest.raises(ValueError, match="application_efficiency must be positive"):
            compute_root_zone(
                theta_current=inp_trigger["theta_current"],
                theta_FC=inp_trigger["theta_FC"],
                theta_WP=inp_trigger["theta_WP"],
                Zr_m=inp_trigger["root_depth_m"],
                TAW_mm=exp_trigger["taw_mm"],
                RAW_mm=exp_trigger["raw_mm"],
                application_efficiency=0.0,  # invalid
                field_area_m2=500.0,
                flow_l_per_min=120.0,
            )

    def test_invalid_flow_raises_only_when_triggered(self):
        """Invalid flow must raise ValueError ONLY when irrigation is triggered."""
        inp_trigger = _golden_inputs("L1-GOLDEN-002")
        exp_trigger = _golden_expected("L1-GOLDEN-002")
        with pytest.raises(ValueError, match="flow_l_per_min must be positive"):
            compute_root_zone(
                theta_current=inp_trigger["theta_current"],
                theta_FC=inp_trigger["theta_FC"],
                theta_WP=inp_trigger["theta_WP"],
                Zr_m=inp_trigger["root_depth_m"],
                TAW_mm=exp_trigger["taw_mm"],
                RAW_mm=exp_trigger["raw_mm"],
                application_efficiency=inp_trigger["application_efficiency"],
                field_area_m2=500.0,
                flow_l_per_min=0.0,   # invalid
            )

    def test_composition_with_t104(self):
        """
        Full composition chain: ET0Input → ET₀ → ETc → water_params → root_zone.

        Uses L1-GOLDEN-002 (trigger=True) to verify the complete Layer 1
        deterministic pipeline from raw sensor inputs to irrigation prescription.
        """
        inp = _golden_inputs("L1-GOLDEN-002")
        exp = _golden_expected("L1-GOLDEN-002")

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

        # T1-05 — root-zone state and prescription
        rz_result = compute_root_zone(
            theta_current=inp["theta_current"],
            theta_FC=inp["theta_FC"],
            theta_WP=inp["theta_WP"],
            Zr_m=inp["root_depth_m"],
            TAW_mm=wp_result.TAW_mm,
            RAW_mm=wp_result.RAW_mm,
            application_efficiency=inp["application_efficiency"],
            field_area_m2=_CALC_AREA_M2,
            flow_l_per_min=_CALC_FLOW_L_MIN,
        )

        assert math.isclose(rz_result.Dr_mm, exp["depletion_mm"], rel_tol=REL_TOL)
        assert rz_result.irrigation_trigger == exp["irrigation_trigger"]
        assert math.isclose(rz_result.I_net_mm, exp["net_irrigation_mm"], rel_tol=REL_TOL)
        assert math.isclose(rz_result.I_gross_mm, exp["gross_irrigation_mm"], rel_tol=REL_TOL)
