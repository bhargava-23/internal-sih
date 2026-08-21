"""
T1-06 — Integration tests for compute_layer1.

These tests verify the full T1-01 → T1-05 pipeline through the unified
compute_layer1 entry point.

Scope:
  - All five golden fixture cases (end-to-end, against approved reference values)
  - Internal consistency checks (ETc == Kc × ET₀, RAW == p × TAW, etc.)
  - Boundary case (Dr == RAW → trigger=True)
  - Normal non-trigger case
  - Irrigation-trigger case
  - High-ET scenario
  - Rain-event scenario (Layer 1 receives effective_rain_mm; it is stored but
    does not affect the deterministic §3.5 depletion equation — rain is applied
    by the simulation water-balance step, not by Layer 1 itself)
  - Repeated identical inputs → identical result
  - All required output fields present
  - Error propagation (invalid config when triggered)

Golden fixture: tests/fixtures/layer1_golden_test_cases.json  (read-only)

Volume/runtime integration fixtures are local calc fixtures, clearly labeled.

Source of truth: docs/05_LAYER1_SPEC.docx §3, §8 / AGENTS.md §20
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from app.domain.layer1.engine import compute_layer1
from app.domain.layer1.types import (
    CropConfig,
    ET0Input,
    Layer1Input,
    Layer1Result,
    SoilConfig,
)

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
# Local integration fixtures
# (for volume/runtime and scenario inputs not present in the golden fixture)
# ---------------------------------------------------------------------------

# Calc fixture: zone geometry and flow — used where the golden fixture
# does not specify area / flow rate.
_INTEG_AREA_M2 = 500.0       # m² — integration fixture only
_INTEG_FLOW_L_MIN = 150.0    # L/min — integration fixture only


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _layer1_input_from_golden(case_id: str) -> Layer1Input:
    """
    Build a Layer1Input from a golden fixture case.

    Area and flow rate are not in the golden fixture; the local integration
    fixture values (_INTEG_AREA_M2, _INTEG_FLOW_L_MIN) are used.
    """
    inp = _GOLDEN[case_id]["inputs"]
    return Layer1Input(
        et0_input=ET0Input(
            T_c=inp["T_c"],
            RH_pct=inp["RH_pct"],
            wind_m_s=inp["wind_m_s"],
            Rn_MJ_m2_day=inp["Rn_MJ_m2_day"],
            elevation_m=inp["elevation_m"],
        ),
        soil=SoilConfig(
            theta_FC=inp["theta_FC"],
            theta_WP=inp["theta_WP"],
            root_depth_m=inp["root_depth_m"],
            zone_area_m2=_INTEG_AREA_M2,
            application_efficiency=inp["application_efficiency"],
            flow_rate_l_min=_INTEG_FLOW_L_MIN,
        ),
        crop=CropConfig(
            Kc=inp["Kc"],
            p_table=inp["p_table"],
        ),
        theta_current=inp["theta_current"],
        effective_rain_mm=0.0,
    )


def _run_golden(case_id: str) -> tuple[Layer1Result, dict]:
    result = compute_layer1(_layer1_input_from_golden(case_id))
    exp = _GOLDEN[case_id]["expected"]
    return result, exp


# ===========================================================================
# Golden fixture — all five end-to-end cases
# ===========================================================================


class TestGoldenCases:
    """End-to-end integration tests against all five golden reference cases."""

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_golden_et0(self, case_id: str):
        result, exp = _run_golden(case_id)
        assert math.isclose(result.et0_mm_day, exp["et0_mm_day"], rel_tol=REL_TOL), (
            f"{case_id}: ET₀={result.et0_mm_day}, expected {exp['et0_mm_day']}"
        )

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_golden_etc(self, case_id: str):
        result, exp = _run_golden(case_id)
        assert math.isclose(result.etc_mm_day, exp["etc_mm_day"], rel_tol=REL_TOL), (
            f"{case_id}: ETc={result.etc_mm_day}, expected {exp['etc_mm_day']}"
        )

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_golden_taw(self, case_id: str):
        result, exp = _run_golden(case_id)
        assert math.isclose(result.taw_mm, exp["taw_mm"], rel_tol=REL_TOL)

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_golden_p(self, case_id: str):
        result, exp = _run_golden(case_id)
        assert math.isclose(result.p, exp["p"], rel_tol=REL_TOL)

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_golden_raw(self, case_id: str):
        result, exp = _run_golden(case_id)
        assert math.isclose(result.raw_mm, exp["raw_mm"], rel_tol=REL_TOL)

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_golden_theta_critical(self, case_id: str):
        result, exp = _run_golden(case_id)
        assert math.isclose(result.theta_critical_m3_m3, exp["theta_critical_m3_m3"], rel_tol=REL_TOL)

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_golden_depletion(self, case_id: str):
        result, exp = _run_golden(case_id)
        assert math.isclose(result.depletion_mm, exp["depletion_mm"], rel_tol=REL_TOL)

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_golden_trigger(self, case_id: str):
        result, exp = _run_golden(case_id)
        assert result.irrigation_trigger == exp["irrigation_trigger"]

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_golden_net_irrigation(self, case_id: str):
        result, exp = _run_golden(case_id)
        assert math.isclose(result.net_irrigation_mm, exp["net_irrigation_mm"], rel_tol=REL_TOL)

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_golden_gross_irrigation(self, case_id: str):
        result, exp = _run_golden(case_id)
        assert math.isclose(result.gross_irrigation_mm, exp["gross_irrigation_mm"], rel_tol=REL_TOL)


# ===========================================================================
# Internal consistency checks
# ===========================================================================


class TestInternalConsistency:
    """
    Verify that the flat Layer1Result fields are internally self-consistent,
    regardless of the specific fixture case.
    """

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_etc_equals_kc_times_et0(self, case_id: str):
        """ETc must equal Kc × ET₀ in every case."""
        result, _ = _run_golden(case_id)
        assert math.isclose(result.etc_mm_day, result.Kc * result.et0_mm_day, rel_tol=REL_TOL), (
            f"{case_id}: ETc={result.etc_mm_day} ≠ Kc×ET₀={result.Kc * result.et0_mm_day}"
        )

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_raw_equals_p_times_taw(self, case_id: str):
        """RAW must equal p × TAW in every case."""
        result, _ = _run_golden(case_id)
        assert math.isclose(result.raw_mm, result.p * result.taw_mm, rel_tol=REL_TOL)

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_trigger_consistent_with_dr_and_raw(self, case_id: str):
        """irrigation_trigger must be True iff depletion_mm >= raw_mm."""
        result, _ = _run_golden(case_id)
        expected_trigger = result.depletion_mm >= result.raw_mm
        assert result.irrigation_trigger == expected_trigger

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_i_net_consistent_with_trigger(self, case_id: str):
        """I_net must be 0 when not triggered and == Dr when triggered."""
        result, _ = _run_golden(case_id)
        if result.irrigation_trigger:
            assert math.isclose(result.net_irrigation_mm, result.depletion_mm, rel_tol=REL_TOL)
        else:
            assert result.net_irrigation_mm == 0.0

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-002", "L1-GOLDEN-004", "L1-GOLDEN-005"],  # triggered cases
    )
    def test_i_gross_equals_i_net_over_ea(self, case_id: str):
        """I_gross == I_net / Ea when irrigation is triggered."""
        result, _ = _run_golden(case_id)
        assert result.irrigation_trigger
        expected_gross = result.net_irrigation_mm / result.application_efficiency
        assert math.isclose(result.gross_irrigation_mm, expected_gross, rel_tol=REL_TOL)

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-002", "L1-GOLDEN-004", "L1-GOLDEN-005"],  # triggered cases
    )
    def test_volume_equals_gross_times_area(self, case_id: str):
        """water_volume_litres must equal gross_irrigation_mm × field_area_m2."""
        result, _ = _run_golden(case_id)
        expected_vol = result.gross_irrigation_mm * result.field_area_m2
        assert math.isclose(result.water_volume_litres, expected_vol, rel_tol=REL_TOL)

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-002", "L1-GOLDEN-004", "L1-GOLDEN-005"],  # triggered cases
    )
    def test_runtime_equals_volume_over_flow(self, case_id: str):
        """valve_runtime_minutes must equal water_volume_litres / flow_rate_l_min."""
        result, _ = _run_golden(case_id)
        expected_runtime = result.water_volume_litres / result.flow_rate_l_min
        assert math.isclose(result.valve_runtime_minutes, expected_runtime, rel_tol=REL_TOL)

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-003"],  # non-triggered cases
    )
    def test_prescription_all_zero_when_no_trigger(self, case_id: str):
        """All prescription outputs must be 0 when no irrigation is triggered."""
        result, _ = _run_golden(case_id)
        assert not result.irrigation_trigger
        assert result.net_irrigation_mm == 0.0
        assert result.gross_irrigation_mm == 0.0
        assert result.water_volume_litres == 0.0
        assert result.valve_runtime_minutes == 0.0


# ===========================================================================
# Boundary case — Dr == RAW
# ===========================================================================


class TestBoundaryCase:
    """L1-GOLDEN-004 is the explicit Dr == RAW boundary case."""

    def test_boundary_trigger_is_true(self):
        """At the exact Dr == RAW boundary, trigger must be True."""
        result, exp = _run_golden("L1-GOLDEN-004")
        assert result.irrigation_trigger is True
        # Verify the fixture encodes a boundary
        assert math.isclose(result.depletion_mm, result.raw_mm, rel_tol=1e-6)

    def test_boundary_net_equals_dr(self):
        """At the boundary, I_net must equal Dr (full-refill)."""
        result, _ = _run_golden("L1-GOLDEN-004")
        assert math.isclose(result.net_irrigation_mm, result.depletion_mm, rel_tol=REL_TOL)


# ===========================================================================
# Named scenario tests
# ===========================================================================


class TestScenarios:
    """
    Additional named-scenario integration tests using explicit Layer1Input
    construction.  These cover: normal monitoring, irrigation trigger,
    high-ET demand, and rain-input passthrough.

    All soil/crop parameters are labeled as calculation fixtures; no
    named-crop Kc or p_table values are invented.
    """

    # ---- Calculation fixture: generic loam zone (not a real crop/soil spec)
    _SOIL_CALC = SoilConfig(
        theta_FC=0.30,         # calc fixture — loam-like
        theta_WP=0.15,         # calc fixture
        root_depth_m=0.60,     # calc fixture
        zone_area_m2=400.0,    # calc fixture
        application_efficiency=0.90,  # calc fixture
        flow_rate_l_min=100.0,  # calc fixture
    )
    _CROP_CALC = CropConfig(
        Kc=0.85,      # calc fixture — mid-season-like
        p_table=0.50, # calc fixture
    )

    def _build(
        self,
        T_c: float,
        RH_pct: float,
        wind_m_s: float,
        Rn_MJ_m2_day: float,
        elevation_m: float,
        theta_current: float,
        effective_rain_mm: float = 0.0,
        soil: SoilConfig | None = None,
        crop: CropConfig | None = None,
    ) -> Layer1Input:
        return Layer1Input(
            et0_input=ET0Input(
                T_c=T_c,
                RH_pct=RH_pct,
                wind_m_s=wind_m_s,
                Rn_MJ_m2_day=Rn_MJ_m2_day,
                elevation_m=elevation_m,
            ),
            soil=soil or self._SOIL_CALC,
            crop=crop or self._CROP_CALC,
            theta_current=theta_current,
            effective_rain_mm=effective_rain_mm,
        )

    def test_normal_non_trigger_case(self):
        """
        Scenario: soil is moderately moist — no irrigation expected.

        θ_current=0.27, θ_FC=0.30, Zr=0.6 → Dr = 18 mm.
        TAW ≈ 90 mm, p≈0.50, RAW ≈ 45 mm → Dr < RAW → no trigger.
        """
        result = compute_layer1(
            self._build(
                T_c=25.0, RH_pct=60.0, wind_m_s=2.0,
                Rn_MJ_m2_day=15.0, elevation_m=200.0,
                theta_current=0.27,
            )
        )
        assert result.irrigation_trigger is False
        assert result.net_irrigation_mm == 0.0
        assert result.water_volume_litres == 0.0
        assert result.valve_runtime_minutes == 0.0

    def test_irrigation_trigger_case(self):
        """
        Scenario: soil is dry enough to trigger irrigation.

        θ_current=0.18, θ_FC=0.30 → Dr = 72 mm.
        TAW ≈ 90 mm, p≈0.50, RAW ≈ 45 mm → Dr > RAW → trigger.
        """
        result = compute_layer1(
            self._build(
                T_c=30.0, RH_pct=40.0, wind_m_s=3.0,
                Rn_MJ_m2_day=18.0, elevation_m=200.0,
                theta_current=0.18,
            )
        )
        assert result.irrigation_trigger is True
        assert result.net_irrigation_mm > 0.0
        assert result.gross_irrigation_mm > result.net_irrigation_mm
        assert result.water_volume_litres > 0.0
        assert result.valve_runtime_minutes > 0.0

    def test_high_et_case(self):
        """
        Scenario: high temperature and radiation → high ET₀ and ETc.

        Verifies that a high-ET input produces an elevated ETc and reduces
        the adjusted p (increases stress sensitivity).
        """
        result = compute_layer1(
            self._build(
                T_c=40.0, RH_pct=25.0, wind_m_s=5.0,
                Rn_MJ_m2_day=25.0, elevation_m=200.0,
                theta_current=0.28,
            )
        )
        # ET₀ must be well above a typical reference at 25°C / 15 MJ
        assert result.et0_mm_day > 6.0
        # ETc == Kc × ET₀ must hold
        assert math.isclose(result.etc_mm_day, result.Kc * result.et0_mm_day, rel_tol=REL_TOL)
        # High ETc reduces p below 0.50 (adjustment makes crop more sensitive)
        assert result.p < 0.50

    def test_rain_input_stored_not_applied_by_layer1(self):
        """
        Scenario: effective_rain_mm is supplied.

        Layer 1 is a deterministic prescription engine; it does not modify
        the root-zone depletion based on current-timestep rainfall — that
        is handled by the simulation water-balance step.  Two identical
        runs with different effective_rain_mm must produce identical Dr and
        trigger outputs (rainfall is stored in the input for traceability
        but Layer 1 §3.5 does not subtract it from Dr).
        """
        dry = self._build(
            T_c=28.0, RH_pct=55.0, wind_m_s=2.5,
            Rn_MJ_m2_day=16.0, elevation_m=200.0,
            theta_current=0.22,
            effective_rain_mm=0.0,
        )
        rainy = self._build(
            T_c=28.0, RH_pct=55.0, wind_m_s=2.5,
            Rn_MJ_m2_day=16.0, elevation_m=200.0,
            theta_current=0.22,
            effective_rain_mm=20.0,   # rain supplied — should not change Dr
        )
        r_dry = compute_layer1(dry)
        r_rain = compute_layer1(rainy)
        # Prescription must be identical — Layer 1 does not apply rainfall
        assert r_dry.depletion_mm == r_rain.depletion_mm
        assert r_dry.irrigation_trigger == r_rain.irrigation_trigger
        assert r_dry.net_irrigation_mm == r_rain.net_irrigation_mm


# ===========================================================================
# Output contract and type checks
# ===========================================================================


class TestOutputContract:
    """Verify Layer1Result type, immutability, and all required fields present."""

    def test_returns_layer1_result_type(self):
        result, _ = _run_golden("L1-GOLDEN-001")
        assert isinstance(result, Layer1Result)

    def test_result_is_frozen(self):
        result, _ = _run_golden("L1-GOLDEN-001")
        with pytest.raises((AttributeError, TypeError)):
            result.et0_mm_day = 0.0  # type: ignore[misc]

    def test_all_atmospheric_fields_present(self):
        result, _ = _run_golden("L1-GOLDEN-001")
        for attr in ("es_kpa", "ea_kpa", "vpd_kpa", "delta_kpa_per_c", "pressure_kpa", "gamma_kpa_per_c"):
            assert hasattr(result, attr)
            assert isinstance(getattr(result, attr), float)

    def test_all_et_fields_present(self):
        result, _ = _run_golden("L1-GOLDEN-001")
        assert isinstance(result.et0_mm_day, float)
        assert isinstance(result.etc_mm_day, float)
        assert isinstance(result.Kc, float)

    def test_all_soil_capacity_fields_present(self):
        result, _ = _run_golden("L1-GOLDEN-001")
        for attr in ("taw_mm", "p", "raw_mm", "theta_critical_m3_m3"):
            assert hasattr(result, attr)

    def test_all_prescription_fields_present(self):
        result, _ = _run_golden("L1-GOLDEN-002")  # triggered case
        assert isinstance(result.water_volume_litres, float)
        assert isinstance(result.valve_runtime_minutes, float)

    def test_all_traceability_echo_fields_present(self):
        result, _ = _run_golden("L1-GOLDEN-001")
        for attr in (
            "theta_FC", "theta_WP", "Zr_m", "theta_current",
            "field_area_m2", "application_efficiency", "flow_rate_l_min",
        ):
            assert hasattr(result, attr)

    def test_echo_fields_match_input(self):
        """Traceability echo fields must reproduce the original input values."""
        inp = _GOLDEN["L1-GOLDEN-001"]["inputs"]
        result, _ = _run_golden("L1-GOLDEN-001")
        assert result.theta_FC == inp["theta_FC"]
        assert result.theta_WP == inp["theta_WP"]
        assert result.Zr_m == inp["root_depth_m"]
        assert result.theta_current == inp["theta_current"]
        assert result.application_efficiency == inp["application_efficiency"]
        assert result.Kc == inp["Kc"]


# ===========================================================================
# Determinism
# ===========================================================================


class TestDeterminism:
    """Identical inputs must always produce identical Layer1Result."""

    @pytest.mark.parametrize(
        "case_id",
        ["L1-GOLDEN-001", "L1-GOLDEN-002", "L1-GOLDEN-003", "L1-GOLDEN-004", "L1-GOLDEN-005"],
    )
    def test_deterministic_on_repeated_call(self, case_id: str):
        result1 = compute_layer1(_layer1_input_from_golden(case_id))
        result2 = compute_layer1(_layer1_input_from_golden(case_id))
        assert result1 == result2


# ===========================================================================
# Error propagation
# ===========================================================================


class TestErrorPropagation:
    """
    Invalid configuration inputs must raise errors from sub-modules
    rather than being silently swallowed by the engine.
    """

    def test_invalid_efficiency_when_triggered_raises(self):
        """
        Zero application efficiency with a dry soil (trigger fires) must
        raise ValueError from T1-05.
        """
        inp = _GOLDEN["L1-GOLDEN-002"]["inputs"]  # trigger=True
        exp = _GOLDEN["L1-GOLDEN-002"]["expected"]
        layer1_inp = Layer1Input(
            et0_input=ET0Input(
                T_c=inp["T_c"],
                RH_pct=inp["RH_pct"],
                wind_m_s=inp["wind_m_s"],
                Rn_MJ_m2_day=inp["Rn_MJ_m2_day"],
                elevation_m=inp["elevation_m"],
            ),
            soil=SoilConfig(
                theta_FC=inp["theta_FC"],
                theta_WP=inp["theta_WP"],
                root_depth_m=inp["root_depth_m"],
                zone_area_m2=500.0,
                application_efficiency=0.0,   # invalid
                flow_rate_l_min=100.0,
            ),
            crop=CropConfig(Kc=inp["Kc"], p_table=inp["p_table"]),
            theta_current=inp["theta_current"],
        )
        with pytest.raises(ValueError, match="application_efficiency"):
            compute_layer1(layer1_inp)

    def test_invalid_flow_when_triggered_raises(self):
        """Zero flow rate with a dry soil must raise ValueError from T1-05."""
        inp = _GOLDEN["L1-GOLDEN-002"]["inputs"]
        layer1_inp = Layer1Input(
            et0_input=ET0Input(
                T_c=inp["T_c"],
                RH_pct=inp["RH_pct"],
                wind_m_s=inp["wind_m_s"],
                Rn_MJ_m2_day=inp["Rn_MJ_m2_day"],
                elevation_m=inp["elevation_m"],
            ),
            soil=SoilConfig(
                theta_FC=inp["theta_FC"],
                theta_WP=inp["theta_WP"],
                root_depth_m=inp["root_depth_m"],
                zone_area_m2=500.0,
                application_efficiency=inp["application_efficiency"],
                flow_rate_l_min=0.0,   # invalid
            ),
            crop=CropConfig(Kc=inp["Kc"], p_table=inp["p_table"]),
            theta_current=inp["theta_current"],
        )
        with pytest.raises(ValueError, match="flow_l_per_min"):
            compute_layer1(layer1_inp)
