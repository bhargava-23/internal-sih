"""
T2-02 — Simulation → Layer 1 integration adapter tests.

Tests cover all 9 required integration test cases:

 1. SCN-001 → Layer 1 executes successfully
 2. SCN-002 → Layer 1 produces an irrigation-triggered result
 3. SCN-003 → Layer 1 executes successfully with forecast-rain field present
 4. SCN-004 → higher ET conditions produce higher ET0/ETc than SCN-001
 5. SCN-005 → Layer 1 still executes independently of hydraulic anomaly
 6. Repeated same scenario/seed produces identical Layer 1 outputs
 7. Simulation state is not mutated unexpectedly by Layer 1
 8. Units are mapped explicitly and correctly
 9. No Layer 1 equations are duplicated

Source of truth:
  docs/02_SIMULATION_PROTOTYPE_SPEC.docx §7
  docs/05_LAYER1_SPEC.docx §2
  AGENTS.md §20
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from app.domain.layer1.types import Layer1Input, Layer1Result
from app.domain.simulation.engine import SimulationRunner
from app.domain.simulation.layer1_adapter import (
    SimLayer1Result,
    ZoneConfig,
    run_layer1_for_state,
    simulation_state_to_layer1_input,
)
from app.domain.simulation.scenarios import get_scenario
from app.domain.simulation.state import SimulationState, ValveState

# ---------------------------------------------------------------------------
# Shared zone config (calc fixture — explicit label)
# Used consistently across all tests so inter-scenario comparisons are fair.
#
# Kc=0.85 / p_table=0.50: mid-season proxy — not crop-specific, calc only.
# elevation_m=150: representative Indian Deccan Plateau site.
# ---------------------------------------------------------------------------

_ZONE = ZoneConfig(
    Kc=0.85,
    p_table=0.50,
    elevation_m=150.0,
    application_efficiency=0.90,
    flow_rate_l_min=5.0,
)

_FIXED_START = datetime(2025, 6, 1, 6, 0, 0, tzinfo=timezone.utc)

REL_TOL = 1e-9


def _runner(scenario_id: str) -> SimulationRunner:
    return SimulationRunner.from_scenario(scenario_id, start_time=_FIXED_START)


def _run_adapter(scenario_id: str, zone: ZoneConfig = _ZONE) -> SimLayer1Result:
    runner = _runner(scenario_id)
    return run_layer1_for_state(runner.current_state, zone)


# ===========================================================================
# Test 1: SCN-001 → Layer 1 executes successfully
# ===========================================================================


class TestSCN001Healthy:
    """SCN-001 healthy monitoring: Layer 1 must run without error."""

    def test_returns_sim_layer1_result_type(self):
        result = _run_adapter("SCN-001")
        assert isinstance(result, SimLayer1Result)

    def test_layer1_result_type(self):
        result = _run_adapter("SCN-001")
        assert isinstance(result.layer1_result, Layer1Result)

    def test_et0_positive(self):
        result = _run_adapter("SCN-001")
        assert result.layer1_result.et0_mm_day > 0.0

    def test_no_irrigation_trigger(self):
        """SCN-001 starts healthy — θ=0.28, loam FC=0.30.
        With p≈0.50 and TAW≈90mm, RAW≈45mm.
        Dr = 1000×(0.30−0.28)×0.6 = 12 mm < RAW → no trigger."""
        result = _run_adapter("SCN-001")
        assert result.layer1_result.irrigation_trigger is False

    def test_net_irrigation_zero(self):
        result = _run_adapter("SCN-001")
        assert result.layer1_result.net_irrigation_mm == 0.0

    def test_simulation_state_echoed(self):
        runner = _runner("SCN-001")
        state = runner.current_state
        result = run_layer1_for_state(state, _ZONE)
        assert result.simulation_state is state


# ===========================================================================
# Test 2: SCN-002 → Layer 1 produces an irrigation-triggered result
# ===========================================================================


class TestSCN002Drying:
    """SCN-002 drying: low initial moisture → trigger must fire."""

    def test_irrigation_trigger_true(self):
        """θ_initial=0.205, loam FC=0.30.
        Dr = 1000×(0.30−0.205)×0.6 = 57 mm.
        With high ETc (~6+ mm), adjusted p is reduced slightly but
        RAW = p×TAW ≈ 0.45×90 = 40.5 mm → Dr > RAW → trigger."""
        result = _run_adapter("SCN-002")
        assert result.layer1_result.irrigation_trigger is True

    def test_net_irrigation_positive(self):
        result = _run_adapter("SCN-002")
        assert result.layer1_result.net_irrigation_mm > 0.0

    def test_gross_irrigation_greater_than_net(self):
        result = _run_adapter("SCN-002")
        l1 = result.layer1_result
        assert l1.gross_irrigation_mm > l1.net_irrigation_mm

    def test_water_volume_positive(self):
        result = _run_adapter("SCN-002")
        assert result.layer1_result.water_volume_litres > 0.0

    def test_valve_runtime_positive(self):
        result = _run_adapter("SCN-002")
        assert result.layer1_result.valve_runtime_minutes > 0.0

    def test_et0_higher_than_scn001_due_to_conditions(self):
        """SCN-002 is hotter and drier → ET₀ must exceed SCN-001."""
        r1 = _run_adapter("SCN-001")
        r2 = _run_adapter("SCN-002")
        assert r2.layer1_result.et0_mm_day > r1.layer1_result.et0_mm_day


# ===========================================================================
# Test 3: SCN-003 → Layer 1 executes with forecast-rain field present
# ===========================================================================


class TestSCN003RainIncoming:
    """SCN-003: moderate moisture + forecast rain."""

    def test_layer1_executes_without_error(self):
        result = _run_adapter("SCN-003")
        assert isinstance(result.layer1_result, Layer1Result)

    def test_et0_positive(self):
        result = _run_adapter("SCN-003")
        assert result.layer1_result.et0_mm_day > 0.0

    def test_forecast_rain_present_in_simulation_state(self):
        runner = _runner("SCN-003")
        cfg = get_scenario("SCN-003")
        assert runner.current_state.forecast_rainfall_next_24h_mm == cfg.forecast.rainfall_next_24h_mm

    def test_no_irrigation_trigger_moderate_moisture(self):
        """SCN-003 starts at θ=0.245.
        Dr = 1000×(0.30−0.245)×0.6 = 33 mm.
        With moderate ETc RAW ≈ 44 mm → Dr < RAW → no trigger."""
        result = _run_adapter("SCN-003")
        assert result.layer1_result.irrigation_trigger is False

    def test_effective_rain_mapped_from_state(self):
        """Layer 1 effective_rain_mm should equal state.rainfall_mm."""
        runner = _runner("SCN-003")
        layer1_input = simulation_state_to_layer1_input(runner.current_state, _ZONE)
        assert layer1_input.effective_rain_mm == runner.current_state.rainfall_mm


# ===========================================================================
# Test 4: SCN-004 → Higher ET conditions produce higher ET0/ETc than SCN-001
# ===========================================================================


class TestSCN004HighET:
    """SCN-004: very hot, dry, high radiation → ET₀ and ETc must exceed SCN-001."""

    def test_et0_higher_than_scn001(self):
        r1 = _run_adapter("SCN-001")
        r4 = _run_adapter("SCN-004")
        assert r4.layer1_result.et0_mm_day > r1.layer1_result.et0_mm_day, (
            f"SCN-004 ET₀={r4.layer1_result.et0_mm_day:.4f} should exceed "
            f"SCN-001 ET₀={r1.layer1_result.et0_mm_day:.4f}"
        )

    def test_etc_higher_than_scn001(self):
        r1 = _run_adapter("SCN-001")
        r4 = _run_adapter("SCN-004")
        assert r4.layer1_result.etc_mm_day > r1.layer1_result.etc_mm_day

    def test_etc_equals_kc_times_et0(self):
        result = _run_adapter("SCN-004")
        l1 = result.layer1_result
        assert math.isclose(l1.etc_mm_day, l1.Kc * l1.et0_mm_day, rel_tol=REL_TOL)

    def test_layer1_executes_without_error(self):
        result = _run_adapter("SCN-004")
        assert isinstance(result.layer1_result, Layer1Result)


# ===========================================================================
# Test 5: SCN-005 → Layer 1 executes independently of hydraulic anomaly
# ===========================================================================


class TestSCN005DeliveryAnomaly:
    """SCN-005: the hydraulic anomaly is a simulation-layer concern.
    Layer 1 must still compute agronomic prescription from the soil state."""

    def test_layer1_executes_without_error(self):
        result = _run_adapter("SCN-005")
        assert isinstance(result.layer1_result, Layer1Result)

    def test_et0_positive(self):
        result = _run_adapter("SCN-005")
        assert result.layer1_result.et0_mm_day > 0.0

    def test_irrigation_trigger_matches_soil_state(self):
        """SCN-005 starts at θ=0.205 — same as SCN-002 → trigger expected."""
        result = _run_adapter("SCN-005")
        assert result.layer1_result.irrigation_trigger is True

    def test_delivery_anomaly_flag_not_in_layer1(self):
        """Layer 1 knows nothing about flow anomaly — it only sees θ and weather."""
        result = _run_adapter("SCN-005")
        # SimulationState has delivery_anomaly flag — Layer1Result does not
        assert not hasattr(result.layer1_result, "delivery_anomaly")

    def test_layer1_input_does_not_see_actual_vs_commanded_flow(self):
        """The Layer1Input must not contain anomaly-specific flow fields."""
        runner = _runner("SCN-005")
        layer1_input = simulation_state_to_layer1_input(runner.current_state, _ZONE)
        assert not hasattr(layer1_input, "actual_flow_l_min")
        assert not hasattr(layer1_input, "commanded_flow_l_min")


# ===========================================================================
# Test 6: Determinism — same scenario/seed → identical Layer 1 outputs
# ===========================================================================


class TestDeterminism:
    """Identical scenario + seed must produce bit-identical Layer 1 results."""

    @pytest.mark.parametrize(
        "scenario_id",
        ["SCN-001", "SCN-002", "SCN-003", "SCN-004", "SCN-005"],
    )
    def test_same_seed_same_layer1_result(self, scenario_id: str):
        r1 = _run_adapter(scenario_id)
        r2 = _run_adapter(scenario_id)
        assert r1.layer1_result == r2.layer1_result, (
            f"{scenario_id}: Layer 1 result differs on repeated run"
        )

    def test_same_seed_same_et0(self):
        r1 = _run_adapter("SCN-001")
        r2 = _run_adapter("SCN-001")
        assert r1.layer1_result.et0_mm_day == r2.layer1_result.et0_mm_day

    def test_different_scenarios_produce_different_et0(self):
        r1 = _run_adapter("SCN-001")
        r4 = _run_adapter("SCN-004")
        assert r1.layer1_result.et0_mm_day != r4.layer1_result.et0_mm_day


# ===========================================================================
# Test 7: Simulation state not mutated by Layer 1
# ===========================================================================


class TestStateMutationSafety:
    """compute_layer1 must not alter the SimulationState it reads from."""

    @pytest.mark.parametrize(
        "scenario_id",
        ["SCN-001", "SCN-002", "SCN-003", "SCN-004", "SCN-005"],
    )
    def test_theta_current_unchanged_after_layer1(self, scenario_id: str):
        runner = _runner(scenario_id)
        theta_before = runner.current_state.theta_current
        run_layer1_for_state(runner.current_state, _ZONE)
        assert runner.current_state.theta_current == theta_before

    @pytest.mark.parametrize(
        "scenario_id",
        ["SCN-001", "SCN-002", "SCN-003", "SCN-004", "SCN-005"],
    )
    def test_valve_state_unchanged_after_layer1(self, scenario_id: str):
        runner = _runner(scenario_id)
        valve_before = runner.current_state.valve_state
        run_layer1_for_state(runner.current_state, _ZONE)
        assert runner.current_state.valve_state == valve_before

    def test_step_index_unchanged_after_layer1(self):
        runner = _runner("SCN-002")
        idx_before = runner.current_state.step_index
        run_layer1_for_state(runner.current_state, _ZONE)
        assert runner.current_state.step_index == idx_before


# ===========================================================================
# Test 8: Units mapped explicitly and correctly
# ===========================================================================


class TestUnitMapping:
    """Verify field-by-field that the adapter correctly maps units."""

    def test_temperature_mapped_to_et0_input(self):
        runner = _runner("SCN-001")
        inp = simulation_state_to_layer1_input(runner.current_state, _ZONE)
        assert inp.et0_input.T_c == runner.current_state.temperature_c

    def test_rh_mapped_to_et0_input(self):
        runner = _runner("SCN-001")
        inp = simulation_state_to_layer1_input(runner.current_state, _ZONE)
        assert inp.et0_input.RH_pct == runner.current_state.relative_humidity_pct

    def test_wind_mapped_to_et0_input(self):
        runner = _runner("SCN-001")
        inp = simulation_state_to_layer1_input(runner.current_state, _ZONE)
        assert inp.et0_input.wind_m_s == runner.current_state.wind_m_s

    def test_radiation_mapped_to_et0_input(self):
        runner = _runner("SCN-001")
        inp = simulation_state_to_layer1_input(runner.current_state, _ZONE)
        assert inp.et0_input.Rn_MJ_m2_day == runner.current_state.radiation_mj_m2_day

    def test_elevation_mapped_from_zone_config(self):
        runner = _runner("SCN-001")
        inp = simulation_state_to_layer1_input(runner.current_state, _ZONE)
        assert inp.et0_input.elevation_m == _ZONE.elevation_m

    def test_theta_current_mapped(self):
        runner = _runner("SCN-002")
        inp = simulation_state_to_layer1_input(runner.current_state, _ZONE)
        assert inp.theta_current == runner.current_state.theta_current

    def test_theta_fc_mapped_from_state(self):
        runner = _runner("SCN-001")
        inp = simulation_state_to_layer1_input(runner.current_state, _ZONE)
        assert inp.soil.theta_FC == runner.current_state.theta_FC

    def test_theta_wp_mapped_from_state(self):
        runner = _runner("SCN-001")
        inp = simulation_state_to_layer1_input(runner.current_state, _ZONE)
        assert inp.soil.theta_WP == runner.current_state.theta_WP

    def test_root_depth_mapped_from_state(self):
        runner = _runner("SCN-001")
        inp = simulation_state_to_layer1_input(runner.current_state, _ZONE)
        assert inp.soil.root_depth_m == runner.current_state.root_zone_depth_m

    def test_field_area_mapped_from_state(self):
        runner = _runner("SCN-001")
        inp = simulation_state_to_layer1_input(runner.current_state, _ZONE)
        assert inp.soil.zone_area_m2 == runner.current_state.field_area_m2

    def test_application_efficiency_from_zone(self):
        runner = _runner("SCN-001")
        inp = simulation_state_to_layer1_input(runner.current_state, _ZONE)
        assert inp.soil.application_efficiency == _ZONE.application_efficiency

    def test_flow_rate_from_zone(self):
        runner = _runner("SCN-001")
        inp = simulation_state_to_layer1_input(runner.current_state, _ZONE)
        assert inp.soil.flow_rate_l_min == _ZONE.flow_rate_l_min

    def test_kc_from_zone(self):
        runner = _runner("SCN-001")
        inp = simulation_state_to_layer1_input(runner.current_state, _ZONE)
        assert inp.crop.Kc == _ZONE.Kc

    def test_p_table_from_zone(self):
        runner = _runner("SCN-001")
        inp = simulation_state_to_layer1_input(runner.current_state, _ZONE)
        assert inp.crop.p_table == _ZONE.p_table

    def test_rainfall_mm_mapped_to_effective_rain(self):
        runner = _runner("SCN-003")
        inp = simulation_state_to_layer1_input(runner.current_state, _ZONE)
        assert inp.effective_rain_mm == runner.current_state.rainfall_mm

    def test_returns_layer1_input_type(self):
        runner = _runner("SCN-001")
        inp = simulation_state_to_layer1_input(runner.current_state, _ZONE)
        assert isinstance(inp, Layer1Input)


# ===========================================================================
# Test 9: No Layer 1 equations duplicated
# ===========================================================================


class TestNoDuplication:
    """
    The adapter must not reproduce any Layer 1 agronomic equations.

    These tests are structural checks — verifying that the adapter output
    equals what compute_layer1() produces for the same input, without
    the adapter needing to compute it independently.
    """

    def test_etc_consistent_with_layer1_definition(self):
        """ETc == Kc × ET₀ — this relationship is enforced by Layer 1, not the adapter."""
        result = _run_adapter("SCN-001")
        l1 = result.layer1_result
        assert math.isclose(l1.etc_mm_day, l1.Kc * l1.et0_mm_day, rel_tol=REL_TOL)

    def test_raw_consistent_with_layer1_definition(self):
        """RAW == p × TAW — enforced by Layer 1."""
        result = _run_adapter("SCN-002")
        l1 = result.layer1_result
        assert math.isclose(l1.raw_mm, l1.p * l1.taw_mm, rel_tol=REL_TOL)

    def test_trigger_consistent_with_depletion_and_raw(self):
        """trigger == (Dr >= RAW) — enforced by Layer 1."""
        for sid in ["SCN-001", "SCN-002"]:
            result = _run_adapter(sid)
            l1 = result.layer1_result
            assert l1.irrigation_trigger == (l1.depletion_mm >= l1.raw_mm)

    def test_gross_consistent_with_net_and_ea(self):
        """I_gross == I_net / Ea when triggered — enforced by Layer 1."""
        result = _run_adapter("SCN-002")
        l1 = result.layer1_result
        assert l1.irrigation_trigger
        assert math.isclose(
            l1.gross_irrigation_mm,
            l1.net_irrigation_mm / l1.application_efficiency,
            rel_tol=REL_TOL,
        )

    def test_adapter_does_not_compute_et0_itself(self):
        """The adapter module must not define ET₀ computations.
        We verify this structurally: the ET₀ in the result matches
        what compute_layer1 returns for the same input, with no
        intermediate calculation in the adapter.
        """
        runner = _runner("SCN-001")
        # Build input manually and call compute_layer1 directly
        from app.domain.layer1.engine import compute_layer1
        inp = simulation_state_to_layer1_input(runner.current_state, _ZONE)
        direct = compute_layer1(inp)
        adapter_result = run_layer1_for_state(runner.current_state, _ZONE)
        # Must be identical — both paths use compute_layer1, no side calculations
        assert adapter_result.layer1_result == direct
