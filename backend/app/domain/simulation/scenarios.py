"""
Simulation — scenario loading.

Reads the approved scenario fixture (tests/fixtures/scenario_fixtures.json)
and converts each entry into a typed ScenarioConfig.

Source of truth: docs/02_SIMULATION_PROTOTYPE_SPEC.docx §4
                 tests/fixtures/scenario_fixtures.json (read-only)

Rules:
  - The fixture file is NEVER modified by this module.
  - All five scenario IDs must load without error.
  - Values from the fixture are mapped directly; no defaults are invented.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.domain.simulation.state import (
    EnvironmentConfig,
    ForecastConfig,
    IrrigationConfig,
    ScenarioConfig,
)

# ---------------------------------------------------------------------------
# Fixture path resolution
# ---------------------------------------------------------------------------

# The fixture file lives at <repo_root>/tests/fixtures/scenario_fixtures.json.
# This module is at <repo_root>/backend/app/domain/simulation/scenarios.py.
# Path: up 5 levels (simulation → domain → app → backend → repo_root)
# then down into tests/fixtures/.
_FIXTURE_PATH = (
    Path(__file__).parent.parent.parent.parent.parent
    / "tests"
    / "fixtures"
    / "scenario_fixtures.json"
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_irrigation(raw: dict) -> IrrigationConfig:
    """
    Parse the 'irrigation' block.

    SCN-001 through SCN-004 use:  flow_l_min, pressure_bar, previous_24h_l
    SCN-005 uses:                 commanded_flow_l_min, actual_flow_l_min,
                                  commanded_pressure_bar, actual_pressure_bar,
                                  previous_24h_l

    For normal scenarios, actual == commanded (no anomaly).
    """
    if "commanded_flow_l_min" in raw:
        # SCN-005 anomaly layout
        return IrrigationConfig(
            flow_l_min=raw["commanded_flow_l_min"],
            actual_flow_l_min=raw["actual_flow_l_min"],
            pressure_bar=raw["commanded_pressure_bar"],
            actual_pressure_bar=raw["actual_pressure_bar"],
            previous_24h_l=raw.get("previous_24h_l", 0.0),
        )
    else:
        # Normal layout — actual == commanded
        return IrrigationConfig(
            flow_l_min=raw["flow_l_min"],
            actual_flow_l_min=raw["flow_l_min"],   # no anomaly
            pressure_bar=raw["pressure_bar"],
            actual_pressure_bar=raw["pressure_bar"],  # no anomaly
            previous_24h_l=raw.get("previous_24h_l", 0.0),
        )


def _parse_scenario(raw: dict) -> ScenarioConfig:
    """Convert one raw fixture dict to a typed ScenarioConfig."""
    env_raw = raw["environment"]
    forecast_raw = raw["forecast"]
    irr_raw = raw["irrigation"]

    return ScenarioConfig(
        id=raw["id"],
        name=raw["name"],
        title=raw["title"],
        seed=raw["seed"],
        duration_hours=raw["duration_hours"],
        crop=raw["crop"],
        growth_stage=raw["growth_stage"],
        soil_texture=raw["soil_texture"],
        root_zone_depth_m=raw["root_zone_depth_m"],
        field_area_m2=raw["field_area_m2"],
        initial_root_zone_moisture=raw["initial_root_zone_moisture"],
        environment=EnvironmentConfig(
            temperature_c=env_raw["temperature_c"],
            relative_humidity_pct=env_raw["relative_humidity_pct"],
            wind_m_s=env_raw["wind_m_s"],
            radiation_mj_m2_day=env_raw["radiation_mj_m2_day"],
            rainfall_mm=env_raw["rainfall_mm"],
        ),
        forecast=ForecastConfig(
            rainfall_next_24h_mm=forecast_raw["rainfall_next_24h_mm"],
            temperature_mean_c=forecast_raw["temperature_mean_c"],
            humidity_mean_pct=forecast_raw["humidity_mean_pct"],
            wind_mean_m_s=forecast_raw["wind_mean_m_s"],
        ),
        irrigation=_parse_irrigation(irr_raw),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_all_scenarios() -> dict[str, ScenarioConfig]:
    """
    Load all scenario fixtures from disk exactly once (cached).

    Returns a dict keyed by scenario ID (e.g. 'SCN-001').
    """
    if not _FIXTURE_PATH.exists():
        raise FileNotFoundError(
            f"Scenario fixture not found: {_FIXTURE_PATH}\n"
            "Ensure tests/fixtures/scenario_fixtures.json is present."
        )
    with _FIXTURE_PATH.open(encoding="utf-8") as f:
        raw_list: list[dict] = json.load(f)

    scenarios: dict[str, ScenarioConfig] = {}
    for raw in raw_list:
        cfg = _parse_scenario(raw)
        scenarios[cfg.id] = cfg

    return scenarios


def get_scenario(scenario_id: str) -> ScenarioConfig:
    """
    Return the ScenarioConfig for the given ID.

    Args:
        scenario_id: One of 'SCN-001' through 'SCN-005'.

    Returns:
        ScenarioConfig loaded from the fixture.

    Raises:
        KeyError: If scenario_id is not found in the fixture.
        FileNotFoundError: If the fixture file is missing.
    """
    all_scenarios = _load_all_scenarios()
    if scenario_id not in all_scenarios:
        available = list(all_scenarios.keys())
        raise KeyError(
            f"Scenario '{scenario_id}' not found.  Available: {available}"
        )
    return all_scenarios[scenario_id]


def list_scenario_ids() -> list[str]:
    """Return all scenario IDs present in the fixture, in order."""
    return list(_load_all_scenarios().keys())
