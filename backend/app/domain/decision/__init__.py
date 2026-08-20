"""
Decision engine — irrigation trigger and water-requirement calculation.

This sub-package will contain:

  engine.py     — evaluate current Dr vs RAW; compute water volume and runtime
  safety.py     — pressure / freshness / flow / override safety gates
  types.py      — DecisionInput, DecisionOutput typed structures

Implementation task: T7-01
Source of truth: docs/04_BACKEND_SCHEMA.docx §3.3 (decisions table),
                 docs/05_LAYER1_SPEC.docx §4 (trigger logic)

RULE: The decision engine receives the Layer 2 forecast as advisory input.
It never allows XGBoost to directly open the valve.
"""
