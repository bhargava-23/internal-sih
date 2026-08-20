"""
pytest configuration and shared fixtures.

This file is discovered automatically by pytest.
It provides fixtures shared across the entire test suite.

Currently only provides:
  - settings override for test environment
  - the path to the golden test fixture files

Domain fixtures (Layer 1 inputs, simulation state, etc.) are added
in their respective test modules during T1-xx and T2-xx tasks.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# Root of the repository (two levels up from backend/tests/)
REPO_ROOT = Path(__file__).parent.parent.parent

# Fixtures directory — these files must never be modified by tests
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


@pytest.fixture(scope="session")
def layer1_golden_cases() -> list[dict]:
    """
    Load the pre-computed Layer 1 golden test cases.

    These cases are the acceptance criteria for the Layer 1 engine.
    They must not be altered during test runs.

    Source: tests/fixtures/layer1_golden_test_cases.json
    """
    fixture_path = FIXTURES_DIR / "layer1_golden_test_cases.json"
    assert fixture_path.exists(), f"Golden test file not found: {fixture_path}"
    with fixture_path.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def scenario_fixtures() -> dict:
    """
    Load the pre-defined simulation scenario fixtures.

    Source: tests/fixtures/scenario_fixtures.json
    """
    fixture_path = FIXTURES_DIR / "scenario_fixtures.json"
    assert fixture_path.exists(), f"Scenario fixture file not found: {fixture_path}"
    with fixture_path.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def test_settings():
    """
    Return the application settings with test overrides.

    Uses the default Settings which read from .env.example defaults
    if no .env is present — safe for CI environments with no secrets.
    """
    from app.config import settings
    return settings
