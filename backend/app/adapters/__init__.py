"""
Adapters — external data and hardware seams.

This sub-package will contain:

  weather_openmeteo.py   — Open-Meteo forecast/archive adapter
                           (the only approved external weather service — TRD)
  simulation_source.py   — simulation telemetry adapter (source=simulation_v1)
  actuator_sim.py        — simulated valve / flow / pressure adapter

Future hardware adapters (MQTT, GSM) are intentionally disabled in V1.
They should be added as new adapter modules behind the same interface
without changing domain logic.

Implementation tasks: T2-03, T2-04, T3-01, T3-02
Source of truth: docs/03_TRD.docx §adapters,
                 docs/04_BACKEND_SCHEMA.docx §telemetry.source enum
"""
