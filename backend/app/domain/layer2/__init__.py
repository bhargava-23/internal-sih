"""
Layer 2 — XGBoost residual forecasting engine.

This sub-package will contain:

  physics_forecast.py  — run Layer 1 forward for 24 h using forecast weather
  feature_builder.py   — lag/rolling/forecast/agronomic feature engineering
  model_loader.py      — load versioned XGBoost artifact from filesystem
  predictor.py         — run inference; return physics + residual + final forecast

Implementation tasks: T4-01, T6-01 through T6-03
Source of truth: docs/06_LAYER2_SPEC.docx

RULE: XGBoost does not command the valve. Layer 1 + decision engine
remain the actuation authority. See AGENTS.md §7.
"""
