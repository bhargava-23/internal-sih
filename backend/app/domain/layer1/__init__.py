"""
Layer 1 — FAO-56-compatible agronomic engine.

This sub-package will contain the deterministic, pure-Python
implementation of the approved equation set:

  atmosphere.py        — es, ea, VPD, Δ, γ, P
  et0.py               — FAO Penman-Monteith daily ET₀
  crop_config.py       — Kc by stage, p_table, root-depth metadata
  water_params.py      — ETc, TAW, adjusted p, RAW, θ_critical
  water_balance.py     — root-zone storage, depletion, balance update
  irrigation_calc.py   — trigger, Inet, Igross, volume, valve runtime
  types.py             — typed input/output data structures

Implementation tasks: T1-01 through T1-08 (docs/10_IMPLEMENTATION_PLAN)
Source of truth: docs/05_LAYER1_SPEC.docx

RULE: No ML code. No FastAPI. No database access. Pure functions only.
"""
