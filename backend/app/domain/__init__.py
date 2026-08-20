"""
Domain layer — pure Python business logic.

Sub-packages:
  layer1/      — FAO-56 agronomic engine (deterministic)
  layer2/      — XGBoost residual forecasting
  decision/    — Irrigation trigger and water-requirement decision
  simulation/  — Deterministic scenario state engine
  feedback/    — Prediction logging and offline retraining metadata

RULE: Domain code must never import FastAPI, SQLAlchemy models,
or React. See AGENTS.md §10 (module ownership table).
"""
