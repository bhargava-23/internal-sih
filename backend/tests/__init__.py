"""
Test package for the AquaSence AI backend.

Sub-packages:
  (none yet — test modules added in later tasks per the implementation plan)

Test categories from AGENTS.md §20:
  - Layer 1: atmosphere, ET₀, Kc, TAW/RAW, depletion, trigger, volume/runtime
  - Layer 2: feature engineering, residual target, temporal split, leakage, XGBoost
  - Simulation: seed reproducibility, timestep, scenario, valve state machine
  - API: health, zones, simulation control, history, model metrics, WebSocket
  - Feedback: prediction/outcome linkage, error calculation

Golden test fixtures (must not be modified):
  tests/fixtures/layer1_golden_test_cases.json
  tests/fixtures/scenario_fixtures.json
"""
