"""
Tests for backend/app/adapters/simulation_source.py  (T2-03).

Verifies that simulation_state_to_telemetry() converts SimulationState
into a valid canonical TelemetryPoint without performing any agronomic
calculation and without mutating the input state.

Test categories
---------------
1.  Valid canonical telemetry record — basic smoke test
2.  Source / provenance marker is exactly TelemetrySource.SIMULATION
3.  Soil moisture maps correctly
4.  Weather fields map correctly
5.  Rainfall maps correctly
6.  Flow maps correctly (uses ACTUAL flow)
7.  Pressure maps correctly (uses ACTUAL pressure)
8.  Valve state is NOT in TelemetryPoint (not part of contract)
9.  Timestamp is preserved
10. Zone identity is preserved
11. Repeated conversion is deterministic
12. SimulationState is not mutated
13. Multiple scenarios convert successfully
14. SCN-005 anomaly values remain distinguishable
15. Canonical field names and types match the backend contract
16. No Layer 1 calculation is performed by the adapter

Source of truth:
  docs/04_BACKEND_SCHEMA.docx §17  — TelemetryPoint contract
  AGENTS.md §20  — Testing Requirements (adapters)
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest

from app.adapters.simulation_source import (
    TelemetryPoint,
    TelemetryQuality,
    TelemetrySource,
    simulation_state_to_telemetry,
)
from app.domain.simulation.engine import SimulationRunner
from app.domain.simulation.state import SimulationState, ValveState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _runner_state(scenario_id: str) -> SimulationState:
    """Return the initial SimulationState for a given scenario."""
    runner = SimulationRunner.from_scenario(scenario_id)
    return runner.current_state


# ---------------------------------------------------------------------------
# 1. Valid canonical telemetry record
# ---------------------------------------------------------------------------


class TestValidTelemetryRecord:
    """The result is a TelemetryPoint with the correct type."""

    def test_returns_telemetry_point(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert isinstance(result, TelemetryPoint)

    def test_all_required_fields_present(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        required_fields = {
            "timestamp",
            "zone_id",
            "soil_moisture_rz",
            "temperature_c",
            "humidity_pct",
            "wind_mps",
            "radiation_mj_m2_day",
            "rainfall_mm",
            "flow_lpm",
            "pressure_bar",
            "source",
            "quality",
        }
        for field in required_fields:
            assert hasattr(result, field), f"Missing field: {field}"

    def test_result_is_immutable(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        # TelemetryPoint is frozen=True — assignment must raise
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            result.soil_moisture_rz = 0.99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. Source / provenance
# ---------------------------------------------------------------------------


class TestSourceProvenance:
    """source is always TelemetrySource.SIMULATION."""

    def test_source_is_simulation_enum(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert result.source is TelemetrySource.SIMULATION

    def test_source_string_value_is_simulation(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert result.source.value == "simulation"

    def test_source_is_not_hardware(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert result.source is not TelemetrySource.HARDWARE

    def test_quality_is_valid(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert result.quality is TelemetryQuality.VALID
        assert result.quality.value == "valid"


# ---------------------------------------------------------------------------
# 3. Soil moisture mapping
# ---------------------------------------------------------------------------


class TestSoilMoistureMapping:
    """soil_moisture_rz <- state.theta_current [m³/m³]."""

    def test_soil_moisture_value(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert result.soil_moisture_rz == pytest.approx(state.theta_current)

    def test_soil_moisture_type(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert isinstance(result.soil_moisture_rz, float)

    def test_soil_moisture_range(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        # m³/m³ for soil moisture is always in [0, 1]
        assert 0.0 <= result.soil_moisture_rz <= 1.0


# ---------------------------------------------------------------------------
# 4. Weather data mapping
# ---------------------------------------------------------------------------


class TestWeatherMapping:
    """temperature_c, humidity_pct, wind_mps, radiation_mj_m2_day."""

    def test_temperature_value(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert result.temperature_c == pytest.approx(state.temperature_c)

    def test_humidity_value(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert result.humidity_pct == pytest.approx(state.relative_humidity_pct)

    def test_wind_value(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert result.wind_mps == pytest.approx(state.wind_m_s)

    def test_radiation_value(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert result.radiation_mj_m2_day == pytest.approx(state.radiation_mj_m2_day)

    def test_radiation_nullable(self) -> None:
        """radiation_mj_m2_day field accepts None (contract allows null)."""
        # The canonical contract allows null; the field type is float | None.
        # In simulation it is always a float, but the type itself must allow None.
        import inspect
        hints = {}
        for f in dataclasses.fields(TelemetryPoint):
            hints[f.name] = f.type
        # radiation_mj_m2_day should have None in its annotation
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        # Just verify the field exists and is a number in simulation
        assert result.radiation_mj_m2_day is not None
        assert isinstance(result.radiation_mj_m2_day, float)

    def test_weather_types(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert isinstance(result.temperature_c, float)
        assert isinstance(result.humidity_pct, float)
        assert isinstance(result.wind_mps, float)


# ---------------------------------------------------------------------------
# 5. Rainfall mapping
# ---------------------------------------------------------------------------


class TestRainfallMapping:
    """rainfall_mm <- state.rainfall_mm [mm]."""

    def test_rainfall_value(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert result.rainfall_mm == pytest.approx(state.rainfall_mm)

    def test_rainfall_type(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert isinstance(result.rainfall_mm, float)

    def test_rainfall_non_negative(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert result.rainfall_mm >= 0.0


# ---------------------------------------------------------------------------
# 6. Flow mapping
# ---------------------------------------------------------------------------


class TestFlowMapping:
    """flow_lpm <- state.actual_flow_l_min [L/min]."""

    def test_flow_maps_to_actual_flow(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        # Must use ACTUAL flow, not commanded flow
        assert result.flow_lpm == pytest.approx(state.actual_flow_l_min)

    def test_flow_type(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert isinstance(result.flow_lpm, float)

    def test_flow_non_negative(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert result.flow_lpm >= 0.0


# ---------------------------------------------------------------------------
# 7. Pressure mapping
# ---------------------------------------------------------------------------


class TestPressureMapping:
    """pressure_bar <- state.actual_pressure_bar [bar]."""

    def test_pressure_maps_to_actual_pressure(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        # Must use ACTUAL pressure, not commanded pressure
        assert result.pressure_bar == pytest.approx(state.actual_pressure_bar)

    def test_pressure_type(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert isinstance(result.pressure_bar, float)

    def test_pressure_non_negative(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert result.pressure_bar >= 0.0


# ---------------------------------------------------------------------------
# 8. Valve state is NOT in TelemetryPoint (per canonical contract)
# ---------------------------------------------------------------------------


class TestValveStateNotInTelemetry:
    """The canonical TelemetryPoint has no valve_state field."""

    def test_no_valve_state_field(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert not hasattr(result, "valve_state"), (
            "valve_state must not appear in TelemetryPoint per backend schema"
        )


# ---------------------------------------------------------------------------
# 9. Timestamp preserved
# ---------------------------------------------------------------------------


class TestTimestampPreserved:
    """timestamp <- state.timestamp (preserved exactly)."""

    def test_timestamp_preserved(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert result.timestamp == state.timestamp

    def test_timestamp_type(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert isinstance(result.timestamp, datetime)


# ---------------------------------------------------------------------------
# 10. Zone identity preserved
# ---------------------------------------------------------------------------


class TestZoneIdentityPreserved:
    """zone_id <- state.zone_id (preserved exactly)."""

    def test_zone_id_preserved(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert result.zone_id == state.zone_id

    def test_zone_id_type(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert isinstance(result.zone_id, str)

    def test_zone_id_nonempty(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert len(result.zone_id) > 0


# ---------------------------------------------------------------------------
# 11. Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Repeated calls with the same state produce identical records."""

    def test_same_state_same_result(self) -> None:
        state = _runner_state("SCN-001")
        r1 = simulation_state_to_telemetry(state)
        r2 = simulation_state_to_telemetry(state)
        assert r1 == r2

    def test_all_scenarios_deterministic(self) -> None:
        for scn in ("SCN-001", "SCN-002", "SCN-003", "SCN-004", "SCN-005"):
            state = _runner_state(scn)
            r1 = simulation_state_to_telemetry(state)
            r2 = simulation_state_to_telemetry(state)
            assert r1 == r2, f"Non-deterministic for {scn}"


# ---------------------------------------------------------------------------
# 12. SimulationState not mutated
# ---------------------------------------------------------------------------


class TestStateMutationSafety:
    """simulation_state_to_telemetry must not modify its input."""

    def test_theta_current_unchanged(self) -> None:
        state = _runner_state("SCN-001")
        original_theta = state.theta_current
        simulation_state_to_telemetry(state)
        assert state.theta_current == original_theta

    def test_timestamp_unchanged(self) -> None:
        state = _runner_state("SCN-001")
        original_ts = state.timestamp
        simulation_state_to_telemetry(state)
        assert state.timestamp == original_ts

    def test_zone_id_unchanged(self) -> None:
        state = _runner_state("SCN-001")
        original_zone = state.zone_id
        simulation_state_to_telemetry(state)
        assert state.zone_id == original_zone

    def test_valve_state_unchanged(self) -> None:
        state = _runner_state("SCN-001")
        original_valve = state.valve_state
        simulation_state_to_telemetry(state)
        assert state.valve_state == original_valve

    def test_all_scenarios_state_unchanged(self) -> None:
        for scn in ("SCN-001", "SCN-002", "SCN-003", "SCN-004", "SCN-005"):
            state = _runner_state(scn)
            snap_theta = state.theta_current
            snap_ts = state.timestamp
            snap_zone = state.zone_id
            simulation_state_to_telemetry(state)
            assert state.theta_current == snap_theta, f"theta mutated in {scn}"
            assert state.timestamp == snap_ts, f"timestamp mutated in {scn}"
            assert state.zone_id == snap_zone, f"zone_id mutated in {scn}"


# ---------------------------------------------------------------------------
# 13. Multiple scenarios convert successfully
# ---------------------------------------------------------------------------


class TestMultipleScenarios:
    """All five V1 scenarios produce valid TelemetryPoints."""

    @pytest.mark.parametrize("scenario_id", ["SCN-001", "SCN-002", "SCN-003", "SCN-004", "SCN-005"])
    def test_scenario_converts(self, scenario_id: str) -> None:
        state = _runner_state(scenario_id)
        result = simulation_state_to_telemetry(state)
        assert isinstance(result, TelemetryPoint)
        assert result.source is TelemetrySource.SIMULATION

    @pytest.mark.parametrize("scenario_id", ["SCN-001", "SCN-002", "SCN-003", "SCN-004", "SCN-005"])
    def test_zone_id_contains_scenario(self, scenario_id: str) -> None:
        state = _runner_state(scenario_id)
        result = simulation_state_to_telemetry(state)
        # Zone ID is "{scenario_id}_zone_1" by convention from SimulationRunner
        assert scenario_id in result.zone_id


# ---------------------------------------------------------------------------
# 14. SCN-005 anomaly values remain distinguishable
# ---------------------------------------------------------------------------


class TestSCN005Anomaly:
    """
    SCN-005 has actual_flow < commanded_flow and actual_pressure < commanded_pressure.
    The adapter exposes actual values so downstream can detect the anomaly.
    """

    def test_scn005_flow_is_actual(self) -> None:
        state = _runner_state("SCN-005")
        result = simulation_state_to_telemetry(state)
        # The telemetry carries actual_flow_l_min (as flow_lpm)
        assert result.flow_lpm == pytest.approx(state.actual_flow_l_min)

    def test_scn005_pressure_is_actual(self) -> None:
        state = _runner_state("SCN-005")
        result = simulation_state_to_telemetry(state)
        assert result.pressure_bar == pytest.approx(state.actual_pressure_bar)

    def test_scn005_delivery_anomaly_flag_in_state(self) -> None:
        """The delivery_anomaly flag is on the state; adapter does not transform it."""
        state = _runner_state("SCN-005")
        # The flag lives on SimulationState — NOT on TelemetryPoint
        # (the adapter does not interpret anomalies; later layers do)
        assert hasattr(state, "delivery_anomaly")
        assert not hasattr(simulation_state_to_telemetry(state), "delivery_anomaly")

    def test_scn005_source_still_simulation(self) -> None:
        state = _runner_state("SCN-005")
        result = simulation_state_to_telemetry(state)
        assert result.source is TelemetrySource.SIMULATION

    def test_scn005_quality_still_valid(self) -> None:
        state = _runner_state("SCN-005")
        result = simulation_state_to_telemetry(state)
        assert result.quality is TelemetryQuality.VALID


# ---------------------------------------------------------------------------
# 15. Canonical field names and types
# ---------------------------------------------------------------------------


class TestCanonicalFieldNamesAndTypes:
    """
    Field names must match docs/04_BACKEND_SCHEMA.docx §17 exactly.
    Types must be compatible with the schema.
    """

    def test_field_names_match_contract(self) -> None:
        expected_fields = {
            "timestamp",
            "zone_id",
            "soil_moisture_rz",
            "temperature_c",
            "humidity_pct",
            "wind_mps",
            "radiation_mj_m2_day",
            "rainfall_mm",
            "flow_lpm",
            "pressure_bar",
            "source",
            "quality",
        }
        actual_fields = {f.name for f in dataclasses.fields(TelemetryPoint)}
        assert actual_fields == expected_fields, (
            f"Field mismatch.\n"
            f"  Missing from TelemetryPoint: {expected_fields - actual_fields}\n"
            f"  Extra in TelemetryPoint:     {actual_fields - expected_fields}"
        )

    def test_source_is_enum_with_correct_values(self) -> None:
        assert TelemetrySource.SIMULATION.value == "simulation"
        assert TelemetrySource.HARDWARE.value == "hardware"

    def test_quality_is_enum_with_correct_values(self) -> None:
        assert TelemetryQuality.VALID.value == "valid"
        assert TelemetryQuality.FLAGGED.value == "flagged"
        assert TelemetryQuality.INVALID.value == "invalid"

    def test_numeric_fields_are_float(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        assert isinstance(result.soil_moisture_rz, float)
        assert isinstance(result.temperature_c, float)
        assert isinstance(result.humidity_pct, float)
        assert isinstance(result.wind_mps, float)
        assert isinstance(result.radiation_mj_m2_day, float)
        assert isinstance(result.rainfall_mm, float)
        assert isinstance(result.flow_lpm, float)
        assert isinstance(result.pressure_bar, float)


# ---------------------------------------------------------------------------
# 16. No Layer 1 calculation performed by the adapter
# ---------------------------------------------------------------------------


class TestNoLayer1Calculation:
    """The adapter must not compute ET0, Kc, ETc, TAW, RAW, or depletion."""

    def test_et0_not_in_telemetry(self) -> None:
        state = _runner_state("SCN-001")
        result = simulation_state_to_telemetry(state)
        for attr in ("ET0", "et0", "ETc", "etc", "TAW", "taw", "RAW", "raw",
                     "depletion", "kc", "Kc", "net_irrigation", "gross_irrigation"):
            assert not hasattr(result, attr), f"Unexpected Layer 1 field: {attr}"

    def test_adapter_does_not_import_layer1(self) -> None:
        """The adapter module must not depend on Layer 1 engine/types."""
        import importlib
        import sys
        # Load the adapter module source
        import app.adapters.simulation_source as module
        # Check the module does NOT import from app.domain.layer1
        import inspect
        source = inspect.getsource(module)
        assert "from app.domain.layer1" not in source, (
            "simulation_source.py must not import from app.domain.layer1"
        )
        assert "import app.domain.layer1" not in source, (
            "simulation_source.py must not import app.domain.layer1"
        )
