"""
T1-03 — Tests for crop evapotranspiration (ETc) and Kc interpolation.

Tests cover:
  - calculate_etc    (low-level: Kc × ET₀ multiplication)
  - compute_etc      (high-level: accepts ET0Result from T1-02)
  - interpolate_kc   (linear stage interpolation)
  - CropDefinition / StageKcConfig schema construction
  - GrowthStage enum values

Reference values for ETc come from the golden fixture:
  tests/fixtures/layer1_golden_test_cases.json

The fixture is read-only.  No Kc numeric values for named crops are
invented in this test module; the fixture supplies Kc directly.

Source of truth: docs/05_LAYER1_SPEC.docx §3.3, §7.1
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from app.domain.layer1.crop_config import (
    CropDefinition,
    GrowthStage,
    StageKcConfig,
)
from app.domain.layer1.etc import ETcResult, calculate_etc, compute_etc, interpolate_kc
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
# Helpers
# ---------------------------------------------------------------------------


def _et0_result_from_golden(case_id: str):
    """Produce an ET0Result from a golden case via the live T1-02 engine."""
    inp_data = _GOLDEN[case_id]["inputs"]
    return compute_et0(
        ET0Input(
            T_c=inp_data["T_c"],
            RH_pct=inp_data["RH_pct"],
            wind_m_s=inp_data["wind_m_s"],
            Rn_MJ_m2_day=inp_data["Rn_MJ_m2_day"],
            elevation_m=inp_data["elevation_m"],
        )
    )


# ===========================================================================
# calculate_etc — low-level ETc = Kc × ET₀
# ===========================================================================


class TestCalculateEtc:
    """Tests for the core ETc multiplication."""

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
    def test_golden_etc_matches_fixture(self, case_id: str):
        """
        ETc must match the expected fixture value when Kc and ET₀ are
        taken directly from the golden case.

        The fixture supplies Kc as a direct numeric input — no crop table
        lookup is performed here.
        """
        inp = _GOLDEN[case_id]["inputs"]
        exp = _GOLDEN[case_id]["expected"]
        Kc = inp["Kc"]
        et0 = exp["et0_mm_day"]
        result = calculate_etc(Kc, et0)
        assert math.isclose(result, exp["etc_mm_day"], rel_tol=REL_TOL), (
            f"{case_id}: ETc={result}, expected {exp['etc_mm_day']}"
        )

    def test_kc_1_gives_et0_unchanged(self):
        """When Kc=1, ETc must equal ET₀ exactly."""
        et0 = 7.390559056795326  # L1-GOLDEN-001 expected ET₀
        result = calculate_etc(1.0, et0)
        assert result == et0

    def test_kc_zero_gives_zero(self):
        """Kc=0 models bare soil with no transpiration; ETc must be 0."""
        result = calculate_etc(0.0, 8.5)
        assert result == 0.0

    def test_higher_kc_gives_higher_etc(self):
        """ETc must scale monotonically with Kc for a fixed ET₀."""
        et0 = 6.0
        assert calculate_etc(0.8, et0) < calculate_etc(1.0, et0) < calculate_etc(1.2, et0)

    def test_deterministic(self):
        assert calculate_etc(1.15, 10.576475672743271) == calculate_etc(
            1.15, 10.576475672743271
        )


# ===========================================================================
# compute_etc — high-level: Kc + ET0Result → ETcResult
# ===========================================================================


class TestComputeEtc:
    """Tests for the high-level compute_etc that accepts ET0Result."""

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
    def test_golden_etc_end_to_end(self, case_id: str):
        """
        End-to-end: ET0Input → compute_et0 → compute_etc → ETc.

        Kc is taken from the golden fixture as a direct numeric value.
        ETc must match the fixture's expected etc_mm_day at rel_tol=1e-9.
        """
        Kc = _GOLDEN[case_id]["inputs"]["Kc"]
        exp_etc = _GOLDEN[case_id]["expected"]["etc_mm_day"]
        et0_result = _et0_result_from_golden(case_id)
        result: ETcResult = compute_etc(Kc, et0_result)

        assert math.isclose(result.etc_mm_day, exp_etc, rel_tol=REL_TOL), (
            f"{case_id}: ETc={result.etc_mm_day}, expected {exp_etc}"
        )

    def test_result_carries_kc_and_et0(self):
        """ETcResult must carry both Kc and ET₀ for traceability."""
        Kc = 1.15
        et0_result = _et0_result_from_golden("L1-GOLDEN-002")
        result = compute_etc(Kc, et0_result)
        assert result.Kc == Kc
        assert math.isclose(result.et0_mm_day, et0_result.et0_mm_day, rel_tol=REL_TOL)

    def test_etc_equals_kc_times_et0(self):
        """ETc stored in result must equal Kc × ET₀ exactly."""
        Kc = 0.85
        et0_result = _et0_result_from_golden("L1-GOLDEN-003")
        result = compute_etc(Kc, et0_result)
        assert math.isclose(
            result.etc_mm_day, Kc * et0_result.et0_mm_day, rel_tol=REL_TOL
        )

    def test_returns_etc_result_type(self):
        """compute_etc must return an ETcResult instance."""
        result = compute_etc(1.0, _et0_result_from_golden("L1-GOLDEN-001"))
        assert isinstance(result, ETcResult)

    def test_frozen_result_is_immutable(self):
        """ETcResult is frozen — mutation must raise."""
        result = compute_etc(1.0, _et0_result_from_golden("L1-GOLDEN-001"))
        with pytest.raises((AttributeError, TypeError)):
            result.etc_mm_day = 0.0  # type: ignore[misc]

    def test_deterministic_on_repeated_call(self):
        """Same inputs must always produce an identical ETcResult."""
        Kc = 1.3
        et0 = _et0_result_from_golden("L1-GOLDEN-005")
        assert compute_etc(Kc, et0) == compute_etc(Kc, et0)


# ===========================================================================
# interpolate_kc — linear stage interpolation
# ===========================================================================


class TestInterpolateKc:
    """
    Tests for Kc(t) = Kc_start + ((t - t0) / duration) × (Kc_end - Kc_start).

    Numeric reference values are computed analytically from the locked
    equation; no crop-specific Kc defaults are used.
    """

    # Common parameters for the interpolation tests
    # Kc values are representative of a transitional stage (e.g., development)
    # but are NOT assigned to any named crop.
    _t0 = 10.0
    _duration = 30.0
    _Kc_start = 0.4   # placeholder — not a named crop value
    _Kc_end = 1.1     # placeholder — not a named crop value

    def test_interpolation_at_stage_start_equals_kc_start(self):
        """At t == t0, result must equal Kc_start exactly."""
        result = interpolate_kc(
            t=self._t0,
            t0=self._t0,
            duration_days=self._duration,
            Kc_start=self._Kc_start,
            Kc_end=self._Kc_end,
        )
        assert math.isclose(result, self._Kc_start, rel_tol=REL_TOL)

    def test_interpolation_at_stage_end_equals_kc_end(self):
        """At t == t0 + duration, result must equal Kc_end exactly."""
        result = interpolate_kc(
            t=self._t0 + self._duration,
            t0=self._t0,
            duration_days=self._duration,
            Kc_start=self._Kc_start,
            Kc_end=self._Kc_end,
        )
        assert math.isclose(result, self._Kc_end, rel_tol=REL_TOL)

    def test_interpolation_at_midpoint(self):
        """At the midpoint (t = t0 + duration/2), Kc must equal the arithmetic mean."""
        t_mid = self._t0 + self._duration / 2.0
        result = interpolate_kc(
            t=t_mid,
            t0=self._t0,
            duration_days=self._duration,
            Kc_start=self._Kc_start,
            Kc_end=self._Kc_end,
        )
        expected_mid = (self._Kc_start + self._Kc_end) / 2.0
        assert math.isclose(result, expected_mid, rel_tol=REL_TOL), (
            f"midpoint Kc={result}, expected {expected_mid}"
        )

    def test_interpolation_equation_correctness(self):
        """
        Spot-check against manual calculation of the equation.

        Kc(t=20) with t0=10, duration=30, Kc_start=0.4, Kc_end=1.1:
            fraction = (20 - 10) / 30 = 1/3
            Kc = 0.4 + (1/3) × (1.1 - 0.4) = 0.4 + 0.2333... = 0.6333...
        """
        result = interpolate_kc(
            t=20.0,
            t0=10.0,
            duration_days=30.0,
            Kc_start=0.4,
            Kc_end=1.1,
        )
        expected = 0.4 + (10.0 / 30.0) * (1.1 - 0.4)
        assert math.isclose(result, expected, rel_tol=REL_TOL), (
            f"Kc(t=20)={result}, expected {expected}"
        )

    def test_flat_stage_returns_constant_kc(self):
        """
        When Kc_start == Kc_end (flat stage such as MID), the result is
        constant regardless of t.
        """
        Kc_flat = 1.05  # not a named crop value
        for t in [0.0, 10.0, 25.0, 50.0]:
            result = interpolate_kc(
                t=t,
                t0=0.0,
                duration_days=40.0,
                Kc_start=Kc_flat,
                Kc_end=Kc_flat,
            )
            assert math.isclose(result, Kc_flat, rel_tol=REL_TOL), (
                f"Flat stage Kc={result} at t={t}, expected {Kc_flat}"
            )

    def test_decreasing_interpolation(self):
        """
        Interpolation handles the case where Kc_start > Kc_end
        (e.g., a LATE stage with declining Kc).
        """
        result = interpolate_kc(
            t=15.0,
            t0=0.0,
            duration_days=20.0,
            Kc_start=1.0,
            Kc_end=0.5,
        )
        expected = 1.0 + (15.0 / 20.0) * (0.5 - 1.0)
        assert math.isclose(result, expected, rel_tol=REL_TOL)

    def test_zero_duration_raises_value_error(self):
        """
        Duration of zero is invalid (§7.1 requires positive integer duration).
        Must raise ValueError.
        """
        with pytest.raises(ValueError, match="duration_days must be positive"):
            interpolate_kc(
                t=5.0,
                t0=0.0,
                duration_days=0.0,
                Kc_start=0.4,
                Kc_end=1.1,
            )

    def test_negative_duration_raises_value_error(self):
        """Negative duration is also invalid."""
        with pytest.raises(ValueError, match="duration_days must be positive"):
            interpolate_kc(
                t=5.0,
                t0=0.0,
                duration_days=-5.0,
                Kc_start=0.4,
                Kc_end=1.1,
            )

    def test_deterministic(self):
        """Same inputs produce the same Kc every time."""
        args = (20.0, 10.0, 30.0, 0.4, 1.1)
        assert interpolate_kc(*args) == interpolate_kc(*args)


# ===========================================================================
# Crop configuration schema
# ===========================================================================


class TestCropConfigSchema:
    """
    Tests for GrowthStage, StageKcConfig, and CropDefinition schema.

    No hard-coded named-crop Kc values are used.  All Kc values below are
    arbitrary placeholders used only to verify schema construction and
    immutability.
    """

    def test_growth_stage_enum_values(self):
        """GrowthStage must expose the four FAO stages as string values."""
        assert GrowthStage.INITIAL.value == "initial"
        assert GrowthStage.DEVELOPMENT.value == "development"
        assert GrowthStage.MID.value == "mid"
        assert GrowthStage.LATE.value == "late"

    def test_stage_kc_config_is_frozen(self):
        """StageKcConfig is a frozen dataclass — mutation must raise."""
        stage = StageKcConfig(
            stage=GrowthStage.MID,
            Kc_start=1.0,
            Kc_end=1.0,
            duration_days=40,
        )
        with pytest.raises((AttributeError, TypeError)):
            stage.Kc_start = 0.5  # type: ignore[misc]

    def test_crop_definition_can_be_constructed(self):
        """
        A CropDefinition can be constructed from arbitrary Kc placeholders.

        This test verifies that the schema is usable without any pre-populated
        crop table.  Numeric values here are not real agronomic data.
        """
        stages = (
            StageKcConfig(GrowthStage.INITIAL, 0.35, 0.35, 25),
            StageKcConfig(GrowthStage.DEVELOPMENT, 0.35, 1.05, 35),
            StageKcConfig(GrowthStage.MID, 1.05, 1.05, 40),
            StageKcConfig(GrowthStage.LATE, 1.05, 0.65, 20),
        )
        crop = CropDefinition(
            crop_id="test_crop_placeholder",
            crop_name="Placeholder Crop (unit test only)",
            stages=stages,
            p_table=0.55,
        )
        assert crop.crop_id == "test_crop_placeholder"
        assert len(crop.stages) == 4
        assert crop.stages[0].stage == GrowthStage.INITIAL
        assert crop.stages[2].stage == GrowthStage.MID
        assert crop.p_table == 0.55

    def test_crop_definition_is_frozen(self):
        """CropDefinition is a frozen dataclass — mutation must raise."""
        crop = CropDefinition(
            crop_id="x",
            crop_name="X",
            stages=(),
            p_table=0.5,
        )
        with pytest.raises((AttributeError, TypeError)):
            crop.crop_id = "y"  # type: ignore[misc]

    def test_stage_duration_stored_correctly(self):
        """StageKcConfig stores duration_days as provided."""
        stage = StageKcConfig(GrowthStage.LATE, 0.9, 0.6, 30)
        assert stage.duration_days == 30

    def test_crop_id_accessible(self):
        """crop_id field is accessible from CropDefinition."""
        crop = CropDefinition(
            crop_id="my_crop_v1",
            crop_name="Test",
            stages=(),
            p_table=0.4,
        )
        assert crop.crop_id == "my_crop_v1"
