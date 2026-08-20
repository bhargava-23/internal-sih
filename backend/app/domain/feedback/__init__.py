"""
Feedback — prediction logging, error tracking and offline retraining.

This sub-package will contain:

  logger.py          — write prediction records before the target is known
  resolver.py        — join the 24h future observation to the prediction record
  metrics.py         — compute error, abs_error, squared_error, rolling MAE/bias
  offline_retrain.py — periodic offline XGBoost retraining workflow

Implementation task: T7-03
Source of truth: docs/07_FEEDBACK_SPEC.docx

RULE: V1 feedback is offline-only. No online retraining, no Kalman,
no ADWIN, no automatic Kc optimization. See AGENTS.md §10.
"""
