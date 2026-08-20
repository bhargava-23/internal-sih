# AquaSence AI V1 — Scenario Fixtures

These fixtures are deterministic demo/integration scenarios for the simulation prototype.

## Required scenarios

- `SCN-001` Healthy Root Zone
- `SCN-002` Drying Field / Irrigation Required
- `SCN-003` Rain Forecast / Irrigation Deferred
- `SCN-004` High ET / Heat Stress
- `SCN-005` Valve / Hydraulic Delivery Anomaly

## Rules

1. Each scenario has a fixed seed for reproducibility.
2. The same scenario and seed must produce repeatable simulation inputs and outcomes.
3. Fixtures define expected **qualitative behavior** unless numeric golden values are explicitly added elsewhere.
4. The scenario engine must run the real Layer 1, physics-forward forecast, XGBoost residual model, decision logic, and feedback path.
5. The frontend must not hard-code scenario outcomes; outcomes must come from backend/simulation state.
6. Scenario files are test/demo fixtures, not field-validation evidence.
7. Do not modify fixture expectations simply to make failing code pass. Investigate the implementation first.

## Suggested file location

```text
data/
└── fixtures/
    └── scenario_fixtures.json
```
