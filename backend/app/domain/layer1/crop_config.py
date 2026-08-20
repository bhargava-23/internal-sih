"""
Layer 1 — Crop and growth-stage configuration schema.

Defines the typed data structures for crop coefficient (Kc) configuration.

This module contains ONLY the schema.  It does NOT contain any hard-coded
numeric Kc values for any named crop.  Actual crop tables are supplied by
the caller (configuration files, simulation setup, test fixtures) so that
the engine remains crop-agnostic.

Source of truth: docs/05_LAYER1_SPEC.docx §3.3, §7.1
Locked design: single-Kc approach, stage-based Kc selection with linear
               interpolation during transitions.

Crop configuration is intentionally kept as plain frozen dataclasses so
that it can be constructed from YAML/JSON configuration files, test
fixtures, or API payloads without coupling to any ORM or file format.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# ---------------------------------------------------------------------------
# Growth stage enumeration
# ---------------------------------------------------------------------------


class GrowthStage(str, Enum):
    """
    FAO-56 compatible growth stage labels.

    Source: docs/05_LAYER1_SPEC.docx §7.1 (stage_sequence field).

    INITIAL     — from sowing/transplanting to ~10% ground cover.
    DEVELOPMENT — rapid canopy development toward full cover.
    MID         — full canopy cover; typically maximum Kc.
    LATE        — senescence and harvest maturity.

    The string values match the labels used in configuration files so that
    JSON/YAML configs can be parsed without a separate mapping table.
    """

    INITIAL = "initial"
    DEVELOPMENT = "development"
    MID = "mid"
    LATE = "late"


# ---------------------------------------------------------------------------
# Per-stage Kc definition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StageKcConfig:
    """
    Crop coefficient parameters for a single growth stage.

    Source: docs/05_LAYER1_SPEC.docx §7.1

    The start and end Kc for a stage define the interpolation range.
    For a flat (non-transitional) stage such as MID, Kc_start == Kc_end.
    For DEVELOPMENT and LATE (transitional), Kc_start != Kc_end.

    Units: Kc is dimensionless (ratio of ETc to ET₀).
    """

    stage: GrowthStage
    """The growth stage this config applies to."""

    Kc_start: float
    """Kc at the beginning of this stage, dimensionless."""

    Kc_end: float
    """Kc at the end of this stage, dimensionless.
    Equal to Kc_start for flat stages (INITIAL, MID).
    """

    duration_days: int
    """Duration of this stage in days.
    Must be a positive integer.  Zero-length stages are not valid.
    """


# ---------------------------------------------------------------------------
# Full crop definition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CropDefinition:
    """
    Complete crop Kc and stage configuration for one crop type.

    Source: docs/05_LAYER1_SPEC.docx §7.1

    This struct is the unit of configuration passed to the Kc/ETc engine.
    It does NOT contain soil parameters (those live in SoilConfig in types.py).

    Numeric Kc values are supplied by the caller from an approved agronomic
    source.  This module does not contain any default Kc values for any
    named crop.
    """

    crop_id: str
    """Unique crop identifier, e.g. 'wheat_drip_v1'."""

    crop_name: str
    """Human-readable crop name, e.g. 'Wheat (drip)'."""

    stages: tuple[StageKcConfig, ...]
    """Ordered sequence of growth stage configurations.
    The order must follow the FAO convention: INITIAL → DEVELOPMENT → MID → LATE.
    Callers are responsible for ordering; the engine does not enforce order.
    """

    p_table: float
    """Baseline allowable depletion fraction from FAO crop table, 0–1.
    ETc-adjusted p is computed in the water-params module (T1-04).
    This field provides the unadjusted p value for that calculation.
    """
