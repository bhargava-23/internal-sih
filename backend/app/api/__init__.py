"""
API layer — FastAPI routers and WebSocket handler.

This sub-package will contain:

  routes_dashboard.py    — zone snapshot, zone list, history (T8-02)
  routes_simulation.py   — start/pause/step/scenario/reset (T8-03)
  routes_model.py        — model metrics, feature importance (T8-04)
  websocket.py           — WebSocket event broadcaster (T8-05)

RULE: Route handlers must not contain domain calculations.
All agronomic, ML and decision logic stays in app/domain/.
See AGENTS.md §12 and docs/04_BACKEND_SCHEMA.docx §24.
"""
