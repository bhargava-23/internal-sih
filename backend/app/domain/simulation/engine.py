"""
Simulation — core field stepping logic.

Implements:
  - SimulationRunner  : the main deterministic state machine
  - _evolve_moisture  : root-zone moisture evolution (no Layer 1 equations)
  - _apply_command    : valve / flow / pressure response
  - _perturb_env      : seeded small environmental variation per step

Design:
  The simulator does NOT compute ET₀, Kc, ETc, TAW, RAW, or irrigation
  decisions.  Those calculations belong to Layer 1.

  The simulator:
    1. Advances the simulated clock by TIMESTEP_MINUTES each step.
    2. Applies seeded environmental perturbation (tiny bounded variation).
    3. Applies any external irrigation command (valve open/close + flow).
    4. Evolves root-zone moisture from the net water balance for the timestep:

         Δθ = (rain_mm + irrigation_mm - evap_demand_mm) / (Zr_m × 1000)

       where evap_demand_mm is a simplified proportional loss derived from
       temperature and radiation — not ET₀ from Layer 1.

    5. Clamps θ to [θ_WP, θ_FC].
    6. Detects delivery anomaly (actual_flow < commanded_flow × threshold).
    7. Returns the new SimulationState.

The moisture evolution model is intentionally simple so the simulator
remains deterministic, bounded, and clearly distinct from random noise.
It produces directionally correct responses:
  - No irrigation → moisture decreases (evaporation-driven depletion).
  - Rain → moisture increases.
  - Irrigation → moisture increases.
  - Higher temperature/radiation → faster depletion.

Source of truth: docs/02_SIMULATION_PROTOTYPE_SPEC.docx §5, §6
AGENTS.md §14 (simulation rules)

No new dependencies; no database; no network; no Layer 1 equations.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.domain.simulation.scenarios import get_scenario
from app.domain.simulation.state import (
    IrrigationCommand,
    ScenarioConfig,
    SimulationState,
    SOIL_PARAMS,
    ValveState,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIMESTEP_MINUTES: int = 60
"""Fixed simulation timestep, minutes."""

# Fraction of commanded_flow below which a delivery anomaly is declared.
# e.g. 0.80 means: if actual < 80% of commanded → anomaly.
ANOMALY_THRESHOLD: float = 0.80

# Environmental perturbation bounds — seeded random, keeps simulation
# realistic without masking the directional signal.
_TEMP_PERTURB_C: float = 0.5        # ±0.5 °C
_RH_PERTURB_PCT: float = 2.0        # ±2 %
_WIND_PERTURB_M_S: float = 0.2      # ±0.2 m/s
_RADIATION_PERTURB: float = 0.3     # ±0.3 MJ/m²/day
_RAIN_PERTURB_MM: float = 0.0       # rain is scenario-driven; no perturbation

# Prototype evaporation demand coefficient.
# Maps (radiation_mj/m2/day) → mm/hour of evaporative demand.
# At 15 MJ/m²/day → ~0.21 mm/h (≈5 mm/day ET₀-like reference).
# At 25 MJ/m²/day → ~0.35 mm/h (≈8.3 mm/day).
# This is a linear approximation used ONLY in the simulator, NOT Layer 1.
# Units: (mm/h) / (MJ/m²/day)
_RAD_EVAP_COEFF: float = 0.014

# Temperature boost: additional evaporation coefficient per °C above 20 °C.
# At 35 °C → +0.015 × 15 = +0.225 mm/h additional depletion (small, directional).
_TEMP_EVAP_COEFF: float = 0.001     # (mm/h) / °C-above-20


# ---------------------------------------------------------------------------
# Core calculation helpers
# ---------------------------------------------------------------------------


def _evaporation_demand_mm_per_hour(temperature_c: float, radiation_mj_m2_day: float) -> float:
    """
    Approximate per-hour evaporation demand, mm/h.

    WHY NOT ET₀: Layer 1 computes the authoritative FAO-56 ET₀.
    This is the simulator's internal simplified demand signal used
    only to drive the direction of θ evolution.

    The value is intentionally lower than full ET₀ to avoid
    overstepping moisture bounds — the simulation runs hourly but
    radiation is a daily figure; we scale accordingly.

    Args:
        temperature_c: Current air temperature, °C.
        radiation_mj_m2_day: Net radiation, MJ/m²/day.

    Returns:
        Evaporative demand, mm/h. Non-negative.
    """
    rad_component = _RAD_EVAP_COEFF * radiation_mj_m2_day
    temp_excess = max(0.0, temperature_c - 20.0)
    temp_component = _TEMP_EVAP_COEFF * temp_excess
    return max(0.0, rad_component + temp_component)


def _evolve_moisture(
    theta: float,
    theta_FC: float,
    theta_WP: float,
    Zr_m: float,
    rain_mm: float,
    irrigation_mm: float,
    evap_demand_mm: float,
) -> float:
    """
    Advance root-zone soil moisture by one timestep.

    Equation:
        Δθ = (rain_mm + irrigation_mm - evap_demand_mm) / (Zr_m × 1000)
        θ_new = clamp(θ + Δθ, θ_WP, θ_FC)

    Units:
        rain_mm, irrigation_mm, evap_demand_mm: mm (per timestep)
        Zr_m: m
        Conversion: 1 mm / (1 m × 1000) = 1 mm / 1000 mm = 0.001 m³/m³
        (because Zr_m × 1000 converts Zr to mm, and mm/mm = dimensionless VWC)

    Args:
        theta: Current VWC, m³/m³.
        theta_FC: Field capacity, m³/m³.
        theta_WP: Wilting point, m³/m³.
        Zr_m: Root-zone depth, m.
        rain_mm: Rainfall this timestep, mm.
        irrigation_mm: Irrigation depth applied this timestep, mm.
        evap_demand_mm: Evaporative loss this timestep, mm.

    Returns:
        New θ clamped to [θ_WP, θ_FC].
    """
    Zr_mm = Zr_m * 1000.0  # m → mm
    delta_theta = (rain_mm + irrigation_mm - evap_demand_mm) / Zr_mm
    theta_new = theta + delta_theta
    return max(theta_WP, min(theta_FC, theta_new))


def _irrigation_depth_this_step(
    actual_flow_l_min: float,
    field_area_m2: float,
    timestep_minutes: float,
) -> float:
    """
    Convert flow rate and duration to an equivalent irrigation depth.

    Equation:
        volume_l = actual_flow_l_min × timestep_minutes
        depth_mm = volume_l / field_area_m2
        (because 1 litre / 1 m² = 1 mm depth)

    Args:
        actual_flow_l_min: Actual flow rate from valve, L/min.
        field_area_m2: Field area, m².
        timestep_minutes: Duration of this timestep, minutes.

    Returns:
        Equivalent irrigation depth, mm.
    """
    volume_l = actual_flow_l_min * timestep_minutes
    return volume_l / field_area_m2


# ---------------------------------------------------------------------------
# SimulationRunner
# ---------------------------------------------------------------------------


class SimulationRunner:
    """
    Deterministic simulation state machine for one scenario.

    Usage::

        runner = SimulationRunner.from_scenario("SCN-002")
        for step in range(24):
            state = runner.current_state
            # ... pass state to Layer 1 ...
            command = IrrigationCommand(open_valve=True, ...)
            runner.step(command)

    The runner is NOT thread-safe and not intended for concurrent use.
    Each call to :meth:`step` advances the simulation by one TIMESTEP_MINUTES
    period and updates :attr:`current_state` in-place.

    Determinism:
        The same scenario_id and the same sequence of IrrigationCommands
        will always produce the same sequence of SimulationState values.
        The seed from the scenario fixture is the only source of randomness.
    """

    def __init__(self, config: ScenarioConfig, start_time: Optional[datetime] = None) -> None:
        """
        Initialize the runner.

        Args:
            config: Fully loaded ScenarioConfig from the fixture.
            start_time: Simulation start time (UTC).  If None, uses a fixed
                        reference time so the run is fully reproducible without
                        depending on the wall clock.
        """
        self._config = config
        self._rng = random.Random(config.seed)

        soil = SOIL_PARAMS.get(config.soil_texture)
        if soil is None:
            raise ValueError(
                f"Soil texture '{config.soil_texture}' not found in SOIL_PARAMS. "
                f"Available: {list(SOIL_PARAMS.keys())}"
            )

        self._theta_FC = soil["theta_FC"]
        self._theta_WP = soil["theta_WP"]

        # Fixed reference start time → fully reproducible timestamps
        if start_time is None:
            start_time = datetime(2025, 6, 1, 6, 0, 0, tzinfo=timezone.utc)

        self.current_state = SimulationState(
            timestamp=start_time,
            step_index=0,
            zone_id=f"{config.id}_zone_1",
            scenario_id=config.id,
            crop=config.crop,
            growth_stage=config.growth_stage,
            soil_texture=config.soil_texture,
            root_zone_depth_m=config.root_zone_depth_m,
            theta_current=config.initial_root_zone_moisture,
            theta_FC=self._theta_FC,
            theta_WP=self._theta_WP,
            temperature_c=config.environment.temperature_c,
            relative_humidity_pct=config.environment.relative_humidity_pct,
            wind_m_s=config.environment.wind_m_s,
            radiation_mj_m2_day=config.environment.radiation_mj_m2_day,
            rainfall_mm=config.environment.rainfall_mm,
            forecast_rainfall_next_24h_mm=config.forecast.rainfall_next_24h_mm,
            forecast_temperature_mean_c=config.forecast.temperature_mean_c,
            forecast_humidity_mean_pct=config.forecast.humidity_mean_pct,
            forecast_wind_mean_m_s=config.forecast.wind_mean_m_s,
            valve_state=ValveState.CLOSED,
            commanded_flow_l_min=0.0,
            actual_flow_l_min=0.0,
            commanded_pressure_bar=0.0,
            actual_pressure_bar=0.0,
            delivered_volume_this_step_l=0.0,
            cumulative_delivered_volume_l=0.0,
            delivery_anomaly=False,
            field_area_m2=config.field_area_m2,
        )

    @classmethod
    def from_scenario(cls, scenario_id: str, start_time: Optional[datetime] = None) -> "SimulationRunner":
        """
        Convenience constructor: load scenario from fixture and create runner.

        Args:
            scenario_id: e.g. 'SCN-001'.
            start_time: Optional fixed start timestamp.

        Returns:
            Initialized SimulationRunner.
        """
        config = get_scenario(scenario_id)
        return cls(config, start_time=start_time)

    def step(self, command: Optional[IrrigationCommand] = None) -> SimulationState:
        """
        Advance the simulation by one TIMESTEP_MINUTES period.

        Steps performed (in order):
          1. Apply seeded environmental perturbation.
          2. Apply irrigation command (valve + flow + pressure).
          3. Compute rain and irrigation depth for this step.
          4. Compute evaporative demand for this step.
          5. Evolve root-zone moisture.
          6. Detect delivery anomaly.
          7. Update timestamp and step index.

        Args:
            command: External irrigation command.  If None, valve stays closed.

        Returns:
            The updated SimulationState (same object as self.current_state).
        """
        s = self.current_state
        cfg = self._config

        # ---- 1. Environmental perturbation (seeded; reproducible) ----------
        temperature_c = s.temperature_c + self._rng.uniform(-_TEMP_PERTURB_C, _TEMP_PERTURB_C)
        relative_humidity_pct = s.relative_humidity_pct + self._rng.uniform(-_RH_PERTURB_PCT, _RH_PERTURB_PCT)
        wind_m_s = max(0.0, s.wind_m_s + self._rng.uniform(-_WIND_PERTURB_M_S, _WIND_PERTURB_M_S))
        radiation_mj_m2_day = max(
            0.0,
            s.radiation_mj_m2_day + self._rng.uniform(-_RADIATION_PERTURB, _RADIATION_PERTURB),
        )
        # Clamp RH to [5, 100]
        relative_humidity_pct = max(5.0, min(100.0, relative_humidity_pct))

        # Rain: use scenario rainfall for every step (constant for prototype).
        # For SCN-003, this keeps initial-state rainfall == 0; the rain
        # *forecast* is what matters for the physics-forward model.
        rainfall_mm_this_step = cfg.environment.rainfall_mm

        # ---- 2. Apply irrigation command -----------------------------------
        if command is not None and command.open_valve:
            valve_state = ValveState.OPEN
            commanded_flow = command.commanded_flow_l_min
            commanded_pressure = command.commanded_pressure_bar
            # SCN-005: actual_flow may differ from commanded (anomaly)
            actual_flow = cfg.irrigation.actual_flow_l_min
            actual_pressure = cfg.irrigation.actual_pressure_bar
        else:
            valve_state = ValveState.CLOSED
            commanded_flow = 0.0
            commanded_pressure = 0.0
            actual_flow = 0.0
            actual_pressure = 0.0

        # ---- 3. Compute irrigation depth for this step ---------------------
        if valve_state == ValveState.OPEN:
            # Use actual_flow — this correctly models the anomaly scenario.
            irr_depth_mm = _irrigation_depth_this_step(
                actual_flow_l_min=actual_flow,
                field_area_m2=cfg.field_area_m2,
                timestep_minutes=TIMESTEP_MINUTES,
            )
            delivered_vol_l = actual_flow * TIMESTEP_MINUTES
        else:
            irr_depth_mm = 0.0
            delivered_vol_l = 0.0

        # ---- 4. Evaporative demand for this step (mm/h × 1 h = mm) --------
        evap_mm = _evaporation_demand_mm_per_hour(temperature_c, radiation_mj_m2_day)
        # * 1.0 because TIMESTEP_MINUTES / 60 = 1.0 (for 60-min step)
        evap_mm *= TIMESTEP_MINUTES / 60.0

        # ---- 5. Evolve root-zone moisture ----------------------------------
        theta_new = _evolve_moisture(
            theta=s.theta_current,
            theta_FC=self._theta_FC,
            theta_WP=self._theta_WP,
            Zr_m=cfg.root_zone_depth_m,
            rain_mm=rainfall_mm_this_step,
            irrigation_mm=irr_depth_mm,
            evap_demand_mm=evap_mm,
        )

        # ---- 6. Delivery anomaly detection ---------------------------------
        # Anomaly: valve is commanded open but actual flow is significantly
        # less than commanded.  Threshold: actual < commanded × ANOMALY_THRESHOLD.
        if valve_state == ValveState.OPEN and commanded_flow > 0.0:
            anomaly = actual_flow < commanded_flow * ANOMALY_THRESHOLD
        else:
            anomaly = False

        # ---- 7. Update pressure when valve is closed -----------------------
        # When closed, actual pressure reports ambient line pressure.
        # For the prototype, use commanded_pressure as the ambient reference.
        if valve_state == ValveState.CLOSED:
            actual_pressure = cfg.irrigation.actual_pressure_bar if cfg.irrigation.actual_pressure_bar > 0 else (
                cfg.irrigation.pressure_bar
            )

        # ---- 8. Advance clock and write state back -------------------------
        new_timestamp = s.timestamp + timedelta(minutes=TIMESTEP_MINUTES)
        new_step = s.step_index + 1
        new_cumulative = s.cumulative_delivered_volume_l + delivered_vol_l

        # Update mutable state in-place
        s.timestamp = new_timestamp
        s.step_index = new_step
        s.temperature_c = temperature_c
        s.relative_humidity_pct = relative_humidity_pct
        s.wind_m_s = wind_m_s
        s.radiation_mj_m2_day = radiation_mj_m2_day
        s.rainfall_mm = rainfall_mm_this_step
        s.theta_current = theta_new
        s.valve_state = valve_state
        s.commanded_flow_l_min = commanded_flow
        s.actual_flow_l_min = actual_flow
        s.commanded_pressure_bar = commanded_pressure
        s.actual_pressure_bar = actual_pressure
        s.delivered_volume_this_step_l = delivered_vol_l
        s.cumulative_delivered_volume_l = new_cumulative
        s.delivery_anomaly = anomaly

        return s
