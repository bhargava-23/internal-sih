"""
Bootstrap smoke tests — T0-01 acceptance criteria.

These tests verify that the project structure is importable
and that the configuration and database session modules load
without errors. They do NOT test domain logic.

Domain tests are added in tasks T1-xx through T8-xx.
"""

from __future__ import annotations

import json
from pathlib import Path


def test_app_is_importable():
    """The FastAPI app instance must be importable without errors."""
    from app.main import app  # noqa: F401
    assert app is not None


def test_config_loads():
    """Settings must load with reasonable defaults."""
    from app.config import settings
    assert settings.app_name == "AquaSence AI"
    assert settings.simulation_seed == 42
    assert settings.ml_target_horizon_hours == 24
    assert 0.0 < settings.default_irrigation_efficiency <= 1.0


def test_database_url_is_sqlite():
    """Database URL must reference SQLite for V1 (TRD requirement)."""
    from app.config import settings
    assert settings.database_url.startswith("sqlite"), (
        "V1 requires SQLite. Do not use a remote database server in V1."
    )


def test_db_session_module_importable():
    """SQLAlchemy session scaffolding must import cleanly."""
    from app.db.session import engine, SessionLocal, Base, get_session  # noqa: F401
    assert engine is not None
    assert SessionLocal is not None


def test_domain_packages_importable():
    """All domain sub-packages must be importable as empty packages."""
    import app.domain.layer1  # noqa: F401
    import app.domain.layer2  # noqa: F401
    import app.domain.decision  # noqa: F401
    import app.domain.simulation  # noqa: F401
    import app.domain.feedback  # noqa: F401
    import app.adapters  # noqa: F401
    import app.api  # noqa: F401


def test_golden_fixture_file_present_and_valid():
    """
    The Layer 1 golden test fixture must be present and parseable.

    This fixture defines the acceptance criteria for the Layer 1
    engine and must never be modified during test runs.
    """
    repo_root = Path(__file__).parent.parent.parent
    fixture_path = repo_root / "tests" / "fixtures" / "layer1_golden_test_cases.json"

    assert fixture_path.exists(), f"Golden fixture missing: {fixture_path}"

    with fixture_path.open(encoding="utf-8") as f:
        cases = json.load(f)

    assert isinstance(cases, list), "Golden fixture must be a JSON array"
    assert len(cases) >= 5, "Expected at least 5 golden test cases"

    for case in cases:
        assert "id" in case, "Each golden case must have an id"
        assert "inputs" in case, "Each golden case must have inputs"
        assert "expected" in case, "Each golden case must have expected"


def test_scenario_fixture_file_present_and_valid():
    """The scenario fixture must be present and parseable."""
    repo_root = Path(__file__).parent.parent.parent
    fixture_path = repo_root / "tests" / "fixtures" / "scenario_fixtures.json"

    assert fixture_path.exists(), f"Scenario fixture missing: {fixture_path}"

    with fixture_path.open(encoding="utf-8") as f:
        data = json.load(f)

    assert data is not None
