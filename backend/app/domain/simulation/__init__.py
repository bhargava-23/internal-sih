"""
Simulation engine — deterministic scenario state machine.

This sub-package will contain:

  state.py        — SimulationState, zone state, simulated clock
  clock.py        — simulation time advancement (step / pause / reset)
  scenarios.py    — five approved scenarios: healthy, drying, rain_incoming,
                    high_et, delivery_anomaly
  field.py        — soil moisture evolution, rainfall/irrigation response
  sensor.py       — generate telemetry readings from SimulationState
  actuator.py     — simulated valve, flow and pressure response

Implementation tasks: T2-01 through T2-04
Source of truth: docs/02_SIMULATION_PROTOTYPE_SPEC.docx,
                 docs/04_BACKEND_SCHEMA.docx §12 (state machine)

RULE: The simulator is deterministic. Every scenario must be
reproducible from its seed. See AGENTS.md §14.
"""
