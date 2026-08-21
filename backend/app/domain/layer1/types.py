"""
Layer 1 — Typed data structures.

All domain types for the agronomic engine live here.
Every input and output struct carries explicit unit documentation so that
calling code cannot silently pass the wrong units.

Source of truth: docs/05_LAYER1_SPEC.docx §2 (inputs) and §3 (outputs)
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Atmospheric inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AtmosphericInput:
    """
    Weather and location inputs required for atmospheric sub-calculations.

    These are the inputs to §3.1 of the Layer 1 spec.
    All values must be in the units documented below.
    No conversion is done inside this struct.
    """

    T_c: float
    """Air temperature, °C."""

    RH_pct: float
    """Relative humidity, % (0–100)."""

    elevation_m: float
    """Site elevation above sea level, m.
    Used to estimate atmospheric pressure when a pressure sensor is absent.
    """


# ---------------------------------------------------------------------------
# Atmospheric outputs — one per calculated atmospheric variable
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AtmosphericResult:
    """
    Outputs of the §3.1 atmospheric variable calculations.

    All values are in SI-derived units consistent with FAO-56.
    """

    es_kpa: float
    """Saturation vapour pressure at the given temperature, kPa."""

    ea_kpa: float
    """Actual vapour pressure, kPa."""

    vpd_kpa: float
    """Vapour pressure deficit (es − ea), kPa."""

    delta_kpa_per_c: float
    """Slope of the saturation vapour-pressure curve (Δ), kPa/°C."""

    pressure_kpa: float
    """Atmospheric pressure estimated from elevation, kPa."""

    gamma_kpa_per_c: float
    """Psychrometric constant (γ), kPa/°C."""


# ---------------------------------------------------------------------------
# ET₀ inputs — extends atmospheric with radiation and wind
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ET0Input:
    """
    Full input set for the FAO Penman-Monteith ET₀ calculation (§3.2).

    Combines atmospheric inputs with radiation and wind inputs.
    """

    T_c: float
    """Air temperature, °C."""

    RH_pct: float
    """Relative humidity, % (0–100)."""

    wind_m_s: float
    """Wind speed at 2 m height, m/s."""

    Rn_MJ_m2_day: float
    """Net radiation at crop surface, MJ/m²/day.
    G (soil heat flux) is approximated as 0 for daily timestep
    per the Layer 1 spec §3.2 prototype convention.
    """

    elevation_m: float
    """Site elevation above sea level, m."""


# ---------------------------------------------------------------------------
# Soil / zone configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SoilConfig:
    """
    Static soil and zone configuration for one irrigation zone.

    Source: docs/05_LAYER1_SPEC.docx §7.2
    """

    theta_FC: float
    """Field capacity volumetric water content, m³/m³."""

    theta_WP: float
    """Wilting point volumetric water content, m³/m³."""

    root_depth_m: float
    """Effective root-zone depth, m."""

    zone_area_m2: float = 100.0
    """Irrigated zone area, m²."""

    application_efficiency: float = 0.90
    """System/application efficiency, dimensionless (0–1).
    Used to convert net irrigation depth to gross applied depth.
    """

    flow_rate_l_min: float = 20.0
    """Nominal zone flow rate, L/min.
    Used to convert target water volume to valve runtime.
    """


# ---------------------------------------------------------------------------
# Crop configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CropConfig:
    """
    Crop-stage parameters for one zone at a given growth stage.

    Source: docs/05_LAYER1_SPEC.docx §7.1
    """

    Kc: float
    """Crop coefficient for the current growth stage, dimensionless."""

    p_table: float
    """Baseline allowable depletion fraction from FAO crop table, 0–1."""


# ---------------------------------------------------------------------------
# Full Layer 1 input bundle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Layer1Input:
    """
    Complete input set for one Layer 1 calculation cycle.

    This is the canonical input type consumed by the full Layer 1 engine
    (implemented across later T1-xx tasks).
    """

    et0_input: ET0Input
    soil: SoilConfig
    crop: CropConfig

    theta_current: float
    """Live volumetric soil moisture from sensor (or simulation), m³/m³."""

    effective_rain_mm: float = 0.0
    """Effective rainfall entering the root zone this timestep, mm.
    Runoff and surface retention losses are already subtracted.
    """


# ---------------------------------------------------------------------------
# Full Layer 1 output bundle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Layer1Result:
    """
    Complete output of one Layer 1 calculation cycle.

    Every intermediate value is preserved so a judge/developer can trace
    the exact path from inputs to valve runtime.

    Source: docs/04_BACKEND_SCHEMA.docx §logging schema,
            docs/05_LAYER1_SPEC.docx §8
    """

    # Atmospheric
    es_kpa: float
    ea_kpa: float
    vpd_kpa: float
    delta_kpa_per_c: float
    pressure_kpa: float
    gamma_kpa_per_c: float

    # ET
    et0_mm_day: float
    etc_mm_day: float

    # Root-zone capacity
    taw_mm: float
    p: float
    raw_mm: float
    theta_critical_m3_m3: float

    # Root-zone state
    depletion_mm: float

    # ET — Kc added for §8 traceability (was missing from the T0-01 draft)
    Kc: float
    """Crop coefficient used for this cycle, dimensionless (input echo)."""

    # Decision
    irrigation_trigger: bool
    net_irrigation_mm: float
    gross_irrigation_mm: float

    # Prescription — outputs introduced by T1-05
    water_volume_litres: float
    """Total water volume required, litres.  0 when no irrigation triggered."""

    valve_runtime_minutes: float
    """Calculated valve open duration, minutes.  0 when no irrigation triggered."""

    # Soil / zone traceability echoes — required by §8 logging schema
    theta_FC: float
    """Field-capacity VWC, m³/m³ (input echo)."""

    theta_WP: float
    """Wilting-point VWC, m³/m³ (input echo)."""

    Zr_m: float
    """Effective root-zone depth, m (input echo)."""

    theta_current: float
    """Current root-zone VWC from sensor/simulation, m³/m³ (input echo)."""

    field_area_m2: float
    """Irrigated zone area, m² (input echo)."""

    application_efficiency: float
    """System application efficiency E_a, dimensionless (input echo)."""

    flow_rate_l_min: float
    """Nominal zone flow rate, L/min (input echo)."""
