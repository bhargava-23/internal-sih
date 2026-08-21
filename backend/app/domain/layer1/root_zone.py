"""
Layer 1 — Root-zone soil state, irrigation prescription, volume, and valve runtime.

Implements §3.5, §3.6, §3.7 (trigger portion), and §3.8 of the Layer 1 spec.

Sequence:
  1. Convert θ_current → Dr  (root-zone depletion in mm, §3.5)
  2. Compare Dr to RAW        (irrigation trigger,      §3.6)
  3. Compute I_net             (target net depth,        §3.8)
  4. Compute I_gross           (gross applied depth,     §3.8)
  5. Compute V_litres          (water volume,            §3.8)
  6. Compute t_valve           (valve runtime,           §3.8)

This module produces the irrigation PRESCRIPTION.
It does NOT actuate, simulate, or command a physical valve.
Actuation is performed by the simulation engine in a later task.

Source of truth: docs/05_LAYER1_SPEC.docx §3.5, §3.6, §3.8
Locked design:  pure deterministic functions; typed inputs/outputs; no side effects.

Unit convention:
  θ_FC, θ_WP, θ_current, θ_critical : m³/m³
  Zr                                  : m
  TAW, RAW, Dr, I_net, I_gross        : mm
  field_area                          : m²
  V_litres                            : litres (1 mm × 1 m² = 1 litre)
  flow_l_per_min                      : L/min
  t_valve                             : minutes
  E_a                                 : dimensionless (0, 1]
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RootZoneResult:
    """
    Complete output of the Layer 1 root-zone irrigation prescription step.

    Carries the current soil state, the trigger decision, the full irrigation
    prescription, and traceability echoes so that downstream modules
    (simulation, feedback logger, Layer 2 features) need not re-compute.

    Source: docs/05_LAYER1_SPEC.docx §3.5, §3.6, §3.8, §8 (logging schema)
    """

    # -- Current soil state (§3.5) ------------------------------------------

    theta_current: float
    """Current root-zone volumetric water content, m³/m³ (sensor input)."""

    Dr_mm: float
    """Root-zone depletion, mm.
    Dr = clip(1000 × (θ_FC − θ_current) × Zr, 0, TAW)
    """

    # -- Trigger (§3.6) -------------------------------------------------------

    irrigation_trigger: bool
    """True when Dr ≥ RAW.  The equality boundary triggers irrigation."""

    # -- Irrigation prescription (§3.8) ----------------------------------------

    I_net_mm: float
    """Net irrigation depth, mm.
    I_net = Dr when triggered, 0 otherwise.
    (Full-refill target: Dtarget = Dr, §3.8)
    """

    I_gross_mm: float
    """Gross applied irrigation depth, mm.
    I_gross = I_net / E_a when triggered, 0 otherwise.
    """

    field_area_m2: float
    """Irrigated field area, m² (input echo)."""

    water_volume_litres: float
    """Total water volume required, litres.
    V = I_gross_mm × field_area_m2  (1 mm × 1 m² = 1 litre, §3.8)
    0 when no irrigation is triggered.
    """

    application_efficiency: float
    """System/application efficiency E_a, dimensionless 0–1 (input echo)."""

    flow_l_per_min: float
    """Nominal zone flow rate, L/min (input echo)."""

    valve_runtime_minutes: float
    """Calculated valve open duration, minutes.
    t_valve = V_litres / flow_l_per_min when irrigation is triggered
              and flow is valid.
    0 when no irrigation is triggered.
    """

    # -- Traceability echoes from T1-04 (for logging/Layer 2 features) --------

    TAW_mm: float
    """Total available water, mm (from T1-04)."""

    RAW_mm: float
    """Readily available water, mm (from T1-04)."""

    theta_FC: float
    """Field-capacity volumetric water content, m³/m³ (input echo)."""

    theta_WP: float
    """Wilting-point volumetric water content, m³/m³ (input echo)."""

    Zr_m: float
    """Effective root-zone depth, m (input echo)."""


# ---------------------------------------------------------------------------
# Individual calculation functions
# ---------------------------------------------------------------------------


def calculate_depletion(
    theta_current: float,
    theta_FC: float,
    Zr_m: float,
    TAW_mm: float,
) -> float:
    """
    Root-zone depletion from the current soil-moisture reading.

    Equation (§3.5):
        Dr = clip(1000 × (θ_FC − θ_current) × Zr, 0, TAW)

    The clipping enforces physical limits:
        θ_current ≥ θ_FC  →  Dr = 0     (soil at or above field capacity)
        θ_current ≤ θ_WP  →  Dr = TAW   (soil at or below wilting point)

    Note: θ_WP is not an explicit argument because the upper clip at TAW
    already captures the wilting-point boundary (TAW = 1000 × (θ_FC − θ_WP) × Zr).

    Args:
        theta_current : Current root-zone volumetric water content, m³/m³.
        theta_FC      : Field-capacity volumetric water content, m³/m³.
        Zr_m          : Effective root-zone depth, m.
        TAW_mm        : Total available water, mm (from T1-04).

    Returns:
        Dr in mm, clipped to [0, TAW_mm].
    """
    dr_raw = 1000.0 * (theta_FC - theta_current) * Zr_m
    return max(0.0, min(TAW_mm, dr_raw))


def check_irrigation_trigger(Dr_mm: float, RAW_mm: float) -> bool:
    """
    Irrigation trigger decision.

    Equation (§3.6):
        Dr >= RAW  →  trigger irrigation
        Dr  < RAW  →  continue monitoring

    The equality boundary MUST trigger irrigation (≥, not >).

    Args:
        Dr_mm  : Current root-zone depletion, mm.
        RAW_mm : Readily available water, mm (from T1-04).

    Returns:
        True when Dr_mm >= RAW_mm.
    """
    return Dr_mm >= RAW_mm


def calculate_net_irrigation(Dr_mm: float, triggered: bool) -> float:
    """
    Target net irrigation depth using the V1 full-refill baseline.

    Equation (§3.8):
        I_net = Dr   when triggered   (Dtarget = Dr, full refill)
        I_net = 0    otherwise

    Args:
        Dr_mm     : Current root-zone depletion, mm.
        triggered : Output of check_irrigation_trigger.

    Returns:
        I_net in mm.
    """
    return Dr_mm if triggered else 0.0


def calculate_gross_irrigation(I_net_mm: float, application_efficiency: float) -> float:
    """
    Gross applied irrigation depth.

    Equation (§3.8):
        I_gross = I_net / E_a

    The gross depth accounts for system losses (drip/sprinkler efficiency).

    Args:
        I_net_mm               : Net irrigation depth, mm.
        application_efficiency : System efficiency E_a, dimensionless (0, 1].
                                 Must be strictly positive to avoid division by zero.

    Returns:
        I_gross in mm.

    Raises:
        ValueError: If application_efficiency <= 0, which is physically invalid
                    and would produce a nonsensical or infinite result.
                    The specification requires E_a to be supplied by configuration;
                    a zero or negative value is a configuration error.
    """
    if application_efficiency <= 0.0:
        raise ValueError(
            f"application_efficiency must be positive, got {application_efficiency!r}. "
            "A zero or negative efficiency is physically invalid (§3.8)."
        )
    return I_net_mm / application_efficiency


def calculate_water_volume(I_gross_mm: float, field_area_m2: float) -> float:
    """
    Total water volume required.

    Equation (§3.8):
        V = I_gross_mm × field_area_m2

    Unit relationship (§3.8):
        1 mm depth × 1 m² area = 1 litre
        (1 mm = 0.001 m; 0.001 m × 1 m² = 0.001 m³ = 1 litre)

    Args:
        I_gross_mm    : Gross irrigation depth, mm.
        field_area_m2 : Irrigated zone area, m².

    Returns:
        Volume in litres.
    """
    return I_gross_mm * field_area_m2


def calculate_valve_runtime(
    water_volume_litres: float,
    flow_l_per_min: float,
) -> float:
    """
    Valve open duration required to deliver the target volume.

    Equation (§3.8):
        t_valve = V_litres / flow_l_per_min

    Only called when irrigation is triggered and the flow rate is valid.

    Args:
        water_volume_litres : Total volume to deliver, litres.
        flow_l_per_min      : Nominal zone flow rate, L/min.
                              Must be strictly positive.

    Returns:
        Valve runtime in minutes.

    Raises:
        ValueError: If flow_l_per_min <= 0, which would produce a nonsensical
                    or infinite result.  The specification requires flow to be
                    "valid and positive" (§3.8) before this calculation is performed.
    """
    if flow_l_per_min <= 0.0:
        raise ValueError(
            f"flow_l_per_min must be positive, got {flow_l_per_min!r}. "
            "The Layer 1 spec §3.8 requires a valid and positive flow rate "
            "before calculating valve runtime."
        )
    return water_volume_litres / flow_l_per_min


# ---------------------------------------------------------------------------
# High-level entry point
# ---------------------------------------------------------------------------


def compute_root_zone(
    theta_current: float,
    theta_FC: float,
    theta_WP: float,
    Zr_m: float,
    TAW_mm: float,
    RAW_mm: float,
    application_efficiency: float,
    field_area_m2: float,
    flow_l_per_min: float,
) -> RootZoneResult:
    """
    Compute the complete root-zone state and irrigation prescription.

    Orchestrates the full §3.5 → §3.6 → §3.8 sequence by delegating to
    the individual functions above.  No equations are duplicated here.

    The application_efficiency and flow_l_per_min are validated only when
    they would actually be used (i.e. when irrigation is triggered).
    If no irrigation is triggered, invalid efficiency/flow values are
    stored in the result for traceability but do NOT raise an error —
    a no-irrigation state requires no prescription computation.

    Args:
        theta_current         : Current root-zone VWC from sensor, m³/m³.
        theta_FC              : Field-capacity VWC, m³/m³.
        theta_WP              : Wilting-point VWC, m³/m³.
        Zr_m                  : Effective root-zone depth, m.
        TAW_mm                : Total available water, mm (T1-04 output).
        RAW_mm                : Readily available water, mm (T1-04 output).
        application_efficiency: System efficiency E_a, dimensionless (0, 1].
        field_area_m2         : Irrigated zone area, m².
        flow_l_per_min        : Nominal zone flow rate, L/min.

    Returns:
        RootZoneResult with complete state, prescription, and traceability.

    Raises:
        ValueError: Only when irrigation IS triggered AND application_efficiency
                    or flow_l_per_min is invalid (≤ 0).
    """
    # Step 1 — Depletion (§3.5)
    dr = calculate_depletion(theta_current, theta_FC, Zr_m, TAW_mm)

    # Step 2 — Trigger (§3.6)
    triggered = check_irrigation_trigger(dr, RAW_mm)

    # Step 3 — Net irrigation (§3.8)
    i_net = calculate_net_irrigation(dr, triggered)

    # Steps 4–6 — Prescription (§3.8); only computed when triggered
    if triggered:
        i_gross = calculate_gross_irrigation(i_net, application_efficiency)
        volume = calculate_water_volume(i_gross, field_area_m2)
        runtime = calculate_valve_runtime(volume, flow_l_per_min)
    else:
        i_gross = 0.0
        volume = 0.0
        runtime = 0.0

    return RootZoneResult(
        theta_current=theta_current,
        Dr_mm=dr,
        irrigation_trigger=triggered,
        I_net_mm=i_net,
        I_gross_mm=i_gross,
        field_area_m2=field_area_m2,
        water_volume_litres=volume,
        application_efficiency=application_efficiency,
        flow_l_per_min=flow_l_per_min,
        valve_runtime_minutes=runtime,
        TAW_mm=TAW_mm,
        RAW_mm=RAW_mm,
        theta_FC=theta_FC,
        theta_WP=theta_WP,
        Zr_m=Zr_m,
    )
