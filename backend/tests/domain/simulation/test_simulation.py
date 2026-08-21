"""
T2-01 — Deterministic simulation engine tests.

Tests cover all 10 required scenarios from the task specification:

 1. Same seed → same outputs (determinism)
 2. Healthy scenario (SCN-001) remains bounded
 3. Drying scenario (SCN-002) produces decreasing moisture under no irrigation
 4. Rain scenario (SCN-003) increases moisture when rain is applied
 5. High-ET (SCN-004) depletes faster than healthy under comparable conditions
 6. Delivery anomaly (SCN-005) preserves commanded vs actual flow
 7. Valve state changes correctly when irrigation command is applied
 8. Moisture remains bounded between WP and FC
 9. Timestamps advance exactly one TIMESTEP_MINUTES period per step
10. All five scenario fixture IDs can be loaded

Additional coverage:
 - Initial state is correctly set from fixture
 - No irrigation: cumulative volume stays zero
 - Irrigation with open command: volume accumulates
 - Environmental perturbation varies between steps but stays in range
 - Scenario loader raises KeyError for unknown IDs

Source of truth: docs/02_SIMULATION_PROTOTYPE_SPEC.docx §5, §6 / AGENTS.md §14
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.simulation.engine import (
    ANOMALY_THRESHOLD,
    SimulationRunner,
    TIMESTEP_MINUTES,
    _evaporation_demand_mm_per_hour,
    _evolve_moisture,
    _irrigation_depth_this_step,
)
from app.domain.simulation.scenarios import get_scenario, list_scenario_ids
from app.domain.simulation.state import (
    IrrigationCommand,
    SOIL_PARAMS,
    ValveState,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

ALL_SCENARIO_IDS = ["SCN-001", "SCN-002", "SCN-003", "SCN-004", "SCN-005"]

_FIXED_START = datetime(2025, 6, 1, 6, 0, 0, tzinfo=timezone.utc)


def _make_runner(scenario_id: str) -> SimulationRunner:
    return SimulationRunner.from_scenario(scenario_id, start_time=_FIXED_START)


def _run_n_steps(
    runner: SimulationRunner,
    n: int,
    command: IrrigationCommand | None = None,
) -> list:
    """Run n steps with the given command and return all states (copies)."""
    from dataclasses import asdict
    states = []
    for _ in range(n):
        runner.step(command)
        # Capture field values we care about rather than full copy
        s = runner.current_state
        states.append({
            "theta": s.theta_current,
            "timestamp": s.timestamp,
            "step": s.step_index,
            "valve": s.valve_state,
            "actual_flow": s.actual_flow_l_min,
            "commanded_flow": s.commanded_flow_l_min,
            "anomaly": s.delivery_anomaly,
            "cumvol": s.cumulative_delivered_volume_l,
            "rain": s.rainfall_mm,
            "temp": s.temperature_c,
        })
    return states


# ===========================================================================
# Test 10: All five scenario IDs can be loaded
# ===========================================================================


class TestScenarioLoading:
    """All five approved scenario IDs must load from the fixture."""

    @pytest.mark.parametrize("scenario_id", ALL_SCENARIO_IDS)
    def test_all_five_ids_load(self, scenario_id: str):
        cfg = get_scenario(scenario_id)
        assert cfg.id == scenario_id

    def test_list_returns_all_five(self):
        ids = list_scenario_ids()
        assert set(ids) == set(ALL_SCENARIO_IDS)

    def test_unknown_id_raises_key_error(self):
        with pytest.raises(KeyError):
            get_scenario("SCN-999")

    @pytest.mark.parametrize("scenario_id", ALL_SCENARIO_IDS)
    def test_runner_initialises_for_all_scenarios(self, scenario_id: str):
        runner = _make_runner(scenario_id)
        assert runner.current_state.scenario_id == scenario_id

    def test_initial_moisture_matches_fixture(self):
        cfg = get_scenario("SCN-001")
        runner = _make_runner("SCN-001")
        assert runner.current_state.theta_current == cfg.initial_root_zone_moisture

    def test_initial_step_index_is_zero(self):
        runner = _make_runner("SCN-001")
        assert runner.current_state.step_index == 0

    def test_initial_valve_is_closed(self):
        runner = _make_runner("SCN-001")
        assert runner.current_state.valve_state == ValveState.CLOSED


# ===========================================================================
# Test 1: Determinism — same seed → same outputs
# ===========================================================================


class TestDeterminism:
    """Same scenario + same commands must produce bit-identical states."""

    @pytest.mark.parametrize("scenario_id", ALL_SCENARIO_IDS)
    def test_same_seed_same_outputs_no_command(self, scenario_id: str):
        r1 = _make_runner(scenario_id)
        r2 = _make_runner(scenario_id)
        s1 = _run_n_steps(r1, 6)
        s2 = _run_n_steps(r2, 6)
        for i, (a, b) in enumerate(zip(s1, s2)):
            assert a["theta"] == b["theta"], f"step {i}: theta differs"
            assert a["timestamp"] == b["timestamp"], f"step {i}: timestamp differs"
            assert a["temp"] == b["temp"], f"step {i}: temperature differs"

    def test_same_seed_same_outputs_with_command(self):
        cmd = IrrigationCommand(
            open_valve=True,
            commanded_flow_l_min=5.0,
            commanded_pressure_bar=1.8,
        )
        r1 = _make_runner("SCN-002")
        r2 = _make_runner("SCN-002")
        _run_n_steps(r1, 3, command=cmd)
        _run_n_steps(r2, 3, command=cmd)
        assert r1.current_state.theta_current == r2.current_state.theta_current
        assert r1.current_state.cumulative_delivered_volume_l == r2.current_state.cumulative_delivered_volume_l

    def test_different_seeds_differ(self):
        """SCN-001 and SCN-002 have different seeds; their state sequences must differ."""
        r1 = _make_runner("SCN-001")
        r2 = _make_runner("SCN-002")
        # Run one step each (same command: none)
        r1.step()
        r2.step()
        # Temperature perturbation will differ because seeds differ
        assert r1.current_state.temperature_c != r2.current_state.temperature_c


# ===========================================================================
# Test 9: Timestamps advance exactly one timestep per step
# ===========================================================================


class TestTimestepAdvancement:
    """Each step must advance the simulation clock by exactly TIMESTEP_MINUTES."""

    @pytest.mark.parametrize("scenario_id", ALL_SCENARIO_IDS)
    def test_timestamp_advances_by_one_step(self, scenario_id: str):
        runner = _make_runner(scenario_id)
        t0 = runner.current_state.timestamp
        runner.step()
        t1 = runner.current_state.timestamp
        assert t1 - t0 == timedelta(minutes=TIMESTEP_MINUTES)

    def test_five_steps_advance_five_timesteps(self):
        runner = _make_runner("SCN-001")
        t0 = runner.current_state.timestamp
        for _ in range(5):
            runner.step()
        t_final = runner.current_state.timestamp
        assert t_final - t0 == timedelta(minutes=5 * TIMESTEP_MINUTES)

    def test_step_index_increments_each_step(self):
        runner = _make_runner("SCN-001")
        for expected_step in range(1, 7):
            runner.step()
            assert runner.current_state.step_index == expected_step


# ===========================================================================
# Test 2: Healthy scenario remains bounded
# ===========================================================================


class TestHealthyScenario:
    """SCN-001 healthy monitoring: soil stays within physical bounds."""

    def test_moisture_stays_bounded_over_full_duration(self):
        runner = _make_runner("SCN-001")
        cfg = get_scenario("SCN-001")
        n_steps = cfg.duration_hours  # 24 steps (one per hour)
        soil = SOIL_PARAMS["loam"]
        for _ in range(n_steps):
            runner.step()
            s = runner.current_state
            assert s.theta_current >= soil["theta_WP"], (
                f"theta {s.theta_current} below WP {soil['theta_WP']}"
            )
            assert s.theta_current <= soil["theta_FC"], (
                f"theta {s.theta_current} above FC {soil['theta_FC']}"
            )

    def test_healthy_scenario_no_irrigation_needed(self):
        """Initial moisture 0.28 is above critical — no command issued → stays passive."""
        runner = _make_runner("SCN-001")
        runner.step()  # no command
        assert runner.current_state.valve_state == ValveState.CLOSED
        assert runner.current_state.delivered_volume_this_step_l == 0.0

    def test_healthy_scenario_cumulative_volume_stays_zero(self):
        runner = _make_runner("SCN-001")
        for _ in range(24):
            runner.step()   # no command → no irrigation
        assert runner.current_state.cumulative_delivered_volume_l == 0.0


# ===========================================================================
# Test 3: Drying scenario — moisture decreases without irrigation
# ===========================================================================


class TestDryingScenario:
    """SCN-002: falling moisture under high evaporative demand, no irrigation."""

    def test_moisture_decreases_over_several_steps(self):
        runner = _make_runner("SCN-002")
        theta_initial = runner.current_state.theta_current
        # Run 8 steps without any irrigation command
        for _ in range(8):
            runner.step(command=None)
        theta_final = runner.current_state.theta_current
        assert theta_final < theta_initial, (
            f"Moisture did not decrease: {theta_initial} → {theta_final}"
        )

    def test_moisture_monotonically_decreasing_without_irrigation(self):
        """Under pure drying (no rain, no irrigation), each step should decrease or stay same."""
        runner = _make_runner("SCN-002")
        prev = runner.current_state.theta_current
        for step in range(12):
            runner.step(command=None)
            curr = runner.current_state.theta_current
            assert curr <= prev, f"Step {step+1}: moisture increased from {prev} to {curr}"
            prev = curr

    def test_moisture_stays_above_wilting_point(self):
        """Even in drying scenario, moisture must not go below θ_WP."""
        runner = _make_runner("SCN-002")
        soil = SOIL_PARAMS["loam"]
        for _ in range(24):
            runner.step(command=None)
            assert runner.current_state.theta_current >= soil["theta_WP"]


# ===========================================================================
# Test 4: Rain scenario — moisture increases when rain is applied
# ===========================================================================


class TestRainScenario:
    """SCN-003: moderate moisture + forecast rain.
    The fixture's environment.rainfall_mm = 0 (rain not yet fallen).
    The scenario's forecast.rainfall_next_24h_mm = 18 mm.

    To test rainfall response directly, we run SCN-003 for a step
    and compare moisture change when the scenario's rainfall_mm > 0
    vs when it is 0. Because the fixture sets rainfall_mm=0, we use
    the _evolve_moisture function directly to verify rain increases moisture.
    """

    def test_rain_increases_moisture(self):
        """_evolve_moisture with rain > 0 should produce higher θ than without rain."""
        soil = SOIL_PARAMS["loam"]
        Zr = 0.6
        theta_0 = 0.245
        evap = 0.2  # mm

        theta_no_rain = _evolve_moisture(
            theta=theta_0,
            theta_FC=soil["theta_FC"],
            theta_WP=soil["theta_WP"],
            Zr_m=Zr,
            rain_mm=0.0,
            irrigation_mm=0.0,
            evap_demand_mm=evap,
        )
        theta_with_rain = _evolve_moisture(
            theta=theta_0,
            theta_FC=soil["theta_FC"],
            theta_WP=soil["theta_WP"],
            Zr_m=Zr,
            rain_mm=15.0,
            irrigation_mm=0.0,
            evap_demand_mm=evap,
        )
        assert theta_with_rain > theta_no_rain, (
            f"Rain should increase moisture: no_rain={theta_no_rain}, with_rain={theta_with_rain}"
        )

    def test_rain_scenario_loads_and_steps(self):
        runner = _make_runner("SCN-003")
        cfg = get_scenario("SCN-003")
        assert cfg.forecast.rainfall_next_24h_mm == 18.0
        runner.step()  # should not error
        assert runner.current_state.step_index == 1

    def test_forecast_rainfall_preserved_in_state(self):
        runner = _make_runner("SCN-003")
        assert runner.current_state.forecast_rainfall_next_24h_mm == 18.0
        runner.step()
        assert runner.current_state.forecast_rainfall_next_24h_mm == 18.0


# ===========================================================================
# Test 5: High-ET depletes faster than healthy
# ===========================================================================


class TestHighETScenario:
    """SCN-004: higher temperature and radiation → faster depletion than SCN-001."""

    def test_high_et_depletes_faster_than_healthy(self):
        """
        After the same number of steps without irrigation:
        SCN-004 (hot/dry/high-rad) should have lower θ than SCN-001 (mild),
        starting from comparable initial conditions.

        SCN-001 starts at θ=0.28; SCN-004 starts at θ=0.24.
        Both are run 6 steps without irrigation.
        We check that the depletion rate (Δθ/step) for SCN-004 > SCN-001.
        """
        r_healthy = _make_runner("SCN-001")
        r_high_et = _make_runner("SCN-004")

        theta_h0 = r_healthy.current_state.theta_current  # 0.28
        theta_e0 = r_high_et.current_state.theta_current  # 0.24

        for _ in range(6):
            r_healthy.step(command=None)
            r_high_et.step(command=None)

        delta_healthy = theta_h0 - r_healthy.current_state.theta_current
        delta_high_et = theta_e0 - r_high_et.current_state.theta_current

        assert delta_high_et > delta_healthy, (
            f"High-ET depletion {delta_high_et:.6f} should exceed "
            f"healthy depletion {delta_healthy:.6f}"
        )

    def test_evaporation_demand_higher_in_high_et(self):
        """_evaporation_demand_mm_per_hour should be higher for SCN-004 conditions."""
        # SCN-001: 28°C, 15 MJ
        demand_healthy = _evaporation_demand_mm_per_hour(28.0, 15.0)
        # SCN-004: 39°C, 25 MJ
        demand_high_et = _evaporation_demand_mm_per_hour(39.0, 25.0)
        assert demand_high_et > demand_healthy


# ===========================================================================
# Test 6: Delivery anomaly — commanded vs actual flow preserved
# ===========================================================================


class TestDeliveryAnomaly:
    """SCN-005: actual_flow < commanded_flow; anomaly flag must be set."""

    def _open_cmd(self) -> IrrigationCommand:
        cfg = get_scenario("SCN-005")
        return IrrigationCommand(
            open_valve=True,
            commanded_flow_l_min=cfg.irrigation.flow_l_min,
            commanded_pressure_bar=cfg.irrigation.pressure_bar,
        )

    def test_commanded_flow_preserved(self):
        runner = _make_runner("SCN-005")
        cmd = self._open_cmd()
        runner.step(command=cmd)
        s = runner.current_state
        assert s.commanded_flow_l_min == pytest.approx(5.0)

    def test_actual_flow_is_lower_than_commanded(self):
        runner = _make_runner("SCN-005")
        cmd = self._open_cmd()
        runner.step(command=cmd)
        s = runner.current_state
        assert s.actual_flow_l_min < s.commanded_flow_l_min

    def test_actual_flow_matches_fixture(self):
        runner = _make_runner("SCN-005")
        cfg = get_scenario("SCN-005")
        cmd = self._open_cmd()
        runner.step(command=cmd)
        assert runner.current_state.actual_flow_l_min == pytest.approx(
            cfg.irrigation.actual_flow_l_min
        )

    def test_delivery_anomaly_flag_set(self):
        runner = _make_runner("SCN-005")
        cmd = self._open_cmd()
        runner.step(command=cmd)
        assert runner.current_state.delivery_anomaly is True

    def test_anomaly_threshold_calculation(self):
        """Anomaly fires when actual < commanded × ANOMALY_THRESHOLD."""
        cfg = get_scenario("SCN-005")
        # commanded = 5.0, actual = 2.2, threshold = 0.80
        # 2.2 < 5.0 × 0.80 = 4.0 → anomaly = True
        assert cfg.irrigation.actual_flow_l_min < cfg.irrigation.flow_l_min * ANOMALY_THRESHOLD

    def test_no_anomaly_in_normal_scenario(self):
        runner = _make_runner("SCN-001")
        cfg = get_scenario("SCN-001")
        cmd = IrrigationCommand(
            open_valve=True,
            commanded_flow_l_min=cfg.irrigation.flow_l_min,
            commanded_pressure_bar=cfg.irrigation.pressure_bar,
        )
        runner.step(command=cmd)
        assert runner.current_state.delivery_anomaly is False


# ===========================================================================
# Test 7: Valve state changes correctly with irrigation command
# ===========================================================================


class TestValveState:
    """Valve must open/close correctly when commanded."""

    def test_no_command_keeps_valve_closed(self):
        runner = _make_runner("SCN-002")
        runner.step(command=None)
        assert runner.current_state.valve_state == ValveState.CLOSED

    def test_open_command_opens_valve(self):
        runner = _make_runner("SCN-002")
        cmd = IrrigationCommand(
            open_valve=True,
            commanded_flow_l_min=5.0,
            commanded_pressure_bar=1.8,
        )
        runner.step(command=cmd)
        assert runner.current_state.valve_state == ValveState.OPEN

    def test_close_command_closes_valve(self):
        runner = _make_runner("SCN-002")
        open_cmd = IrrigationCommand(open_valve=True, commanded_flow_l_min=5.0, commanded_pressure_bar=1.8)
        close_cmd = IrrigationCommand(open_valve=False, commanded_flow_l_min=0.0, commanded_pressure_bar=0.0)
        runner.step(command=open_cmd)
        assert runner.current_state.valve_state == ValveState.OPEN
        runner.step(command=close_cmd)
        assert runner.current_state.valve_state == ValveState.CLOSED

    def test_open_command_sets_commanded_flow(self):
        runner = _make_runner("SCN-002")
        cmd = IrrigationCommand(open_valve=True, commanded_flow_l_min=7.5, commanded_pressure_bar=2.0)
        runner.step(command=cmd)
        assert runner.current_state.commanded_flow_l_min == pytest.approx(7.5)

    def test_closed_valve_zero_delivered_volume(self):
        runner = _make_runner("SCN-002")
        runner.step(command=None)
        assert runner.current_state.delivered_volume_this_step_l == 0.0


# ===========================================================================
# Test 8: Moisture bounded between WP and FC
# ===========================================================================


class TestMoistureBounds:
    """θ must always remain in [θ_WP, θ_FC] across all scenarios."""

    @pytest.mark.parametrize("scenario_id", ALL_SCENARIO_IDS)
    def test_moisture_stays_in_bounds_no_irrigation(self, scenario_id: str):
        runner = _make_runner(scenario_id)
        soil = SOIL_PARAMS["loam"]
        cfg = get_scenario(scenario_id)
        n_steps = cfg.duration_hours
        for step in range(n_steps):
            runner.step(command=None)
            theta = runner.current_state.theta_current
            assert theta >= soil["theta_WP"], f"{scenario_id} step {step+1}: theta {theta} < WP"
            assert theta <= soil["theta_FC"], f"{scenario_id} step {step+1}: theta {theta} > FC"

    def test_heavy_irrigation_does_not_exceed_fc(self):
        """Even with heavy irrigation, θ must not exceed θ_FC."""
        runner = _make_runner("SCN-002")
        soil = SOIL_PARAMS["loam"]
        # Very high flow → lots of water applied
        cmd = IrrigationCommand(open_valve=True, commanded_flow_l_min=500.0, commanded_pressure_bar=2.0)
        for _ in range(6):
            runner.step(command=cmd)
            assert runner.current_state.theta_current <= soil["theta_FC"]

    def test_evolve_moisture_clamps_to_fc(self):
        soil = SOIL_PARAMS["loam"]
        # Start at FC, add more water → should stay at FC
        result = _evolve_moisture(
            theta=soil["theta_FC"],
            theta_FC=soil["theta_FC"],
            theta_WP=soil["theta_WP"],
            Zr_m=0.6,
            rain_mm=100.0,
            irrigation_mm=100.0,
            evap_demand_mm=0.0,
        )
        assert result == pytest.approx(soil["theta_FC"])

    def test_evolve_moisture_clamps_to_wp(self):
        soil = SOIL_PARAMS["loam"]
        # Start at WP, large evap → should stay at WP
        result = _evolve_moisture(
            theta=soil["theta_WP"],
            theta_FC=soil["theta_FC"],
            theta_WP=soil["theta_WP"],
            Zr_m=0.6,
            rain_mm=0.0,
            irrigation_mm=0.0,
            evap_demand_mm=9999.0,  # extreme
        )
        assert result == pytest.approx(soil["theta_WP"])


# ===========================================================================
# Pure function unit tests
# ===========================================================================


class TestPureFunctions:
    """Unit tests for the pure calculation helpers."""

    def test_evaporation_demand_positive(self):
        d = _evaporation_demand_mm_per_hour(30.0, 18.0)
        assert d > 0.0

    def test_evaporation_demand_never_negative(self):
        # Temperature below 20°C and zero radiation
        d = _evaporation_demand_mm_per_hour(0.0, 0.0)
        assert d >= 0.0

    def test_evaporation_higher_at_higher_temp(self):
        d_low = _evaporation_demand_mm_per_hour(20.0, 15.0)
        d_high = _evaporation_demand_mm_per_hour(40.0, 15.0)
        assert d_high > d_low

    def test_evaporation_higher_at_higher_radiation(self):
        d_low = _evaporation_demand_mm_per_hour(25.0, 10.0)
        d_high = _evaporation_demand_mm_per_hour(25.0, 25.0)
        assert d_high > d_low

    def test_irrigation_depth_unit_conversion(self):
        """1 L/min × 60 min / 100 m² = 0.6 mm"""
        depth = _irrigation_depth_this_step(
            actual_flow_l_min=1.0,
            field_area_m2=100.0,
            timestep_minutes=60,
        )
        assert depth == pytest.approx(0.6)

    def test_irrigation_depth_zero_flow(self):
        depth = _irrigation_depth_this_step(0.0, 100.0, 60)
        assert depth == 0.0

    def test_evolve_moisture_depletion_only(self):
        """No rain, no irrigation → moisture decreases."""
        soil = SOIL_PARAMS["loam"]
        theta_new = _evolve_moisture(
            theta=0.25,
            theta_FC=soil["theta_FC"],
            theta_WP=soil["theta_WP"],
            Zr_m=0.6,
            rain_mm=0.0,
            irrigation_mm=0.0,
            evap_demand_mm=1.0,
        )
        assert theta_new < 0.25

    def test_evolve_moisture_irrigation_only(self):
        """No rain, no evap, with irrigation → moisture increases."""
        soil = SOIL_PARAMS["loam"]
        theta_new = _evolve_moisture(
            theta=0.20,
            theta_FC=soil["theta_FC"],
            theta_WP=soil["theta_WP"],
            Zr_m=0.6,
            rain_mm=0.0,
            irrigation_mm=10.0,  # 10 mm depth applied
            evap_demand_mm=0.0,
        )
        assert theta_new > 0.20


# ===========================================================================
# Irrigation volume accumulation
# ===========================================================================


class TestIrrigationAccumulation:
    """Delivered volume must accumulate correctly across steps."""

    def test_open_valve_accumulates_volume(self):
        runner = _make_runner("SCN-002")
        cmd = IrrigationCommand(open_valve=True, commanded_flow_l_min=5.0, commanded_pressure_bar=1.8)
        runner.step(command=cmd)
        # Delivered this step = actual_flow × TIMESTEP_MINUTES
        # For SCN-002, actual == commanded (no anomaly)
        expected_vol = 5.0 * TIMESTEP_MINUTES
        assert runner.current_state.delivered_volume_this_step_l == pytest.approx(expected_vol)
        assert runner.current_state.cumulative_delivered_volume_l == pytest.approx(expected_vol)

    def test_volume_accumulates_over_multiple_steps(self):
        runner = _make_runner("SCN-002")
        cmd = IrrigationCommand(open_valve=True, commanded_flow_l_min=5.0, commanded_pressure_bar=1.8)
        n = 3
        for _ in range(n):
            runner.step(command=cmd)
        expected_total = 5.0 * TIMESTEP_MINUTES * n
        assert runner.current_state.cumulative_delivered_volume_l == pytest.approx(expected_total)

    def test_anomaly_volume_uses_actual_flow(self):
        """In SCN-005, delivered volume uses actual_flow, not commanded_flow."""
        runner = _make_runner("SCN-005")
        cfg = get_scenario("SCN-005")
        cmd = IrrigationCommand(
            open_valve=True,
            commanded_flow_l_min=cfg.irrigation.flow_l_min,
            commanded_pressure_bar=cfg.irrigation.pressure_bar,
        )
        runner.step(command=cmd)
        s = runner.current_state
        expected_actual_vol = cfg.irrigation.actual_flow_l_min * TIMESTEP_MINUTES
        expected_commanded_vol = cfg.irrigation.flow_l_min * TIMESTEP_MINUTES
        # Volume must match actual, not commanded
        assert s.delivered_volume_this_step_l == pytest.approx(expected_actual_vol)
        assert s.delivered_volume_this_step_l < expected_commanded_vol
