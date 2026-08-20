# AquaSence AI — Golden Layer 1 Test Cases

## Purpose
Deterministic regression fixtures for the Layer 1 agronomic engine. These tests protect ET₀, Kc, ETc, TAW, p, RAW, depletion, trigger and irrigation calculations.

## Fixture note
`Kc`, `p_table`, FC and WP values here are test fixtures, not universal crop/soil claims. Production configuration must use the approved Layer 1 tables.

## Locked formulas under test
```text
es = 0.6108 * exp(17.27*T / (T + 237.3))
ea = es * RH / 100
Delta = 4098*es / (T + 237.3)^2
P = 101.3 * ((293 - 0.0065*z)/293)^5.26
gamma = 0.000665 * P
ET0 = [0.408*Delta*(Rn-G) + gamma*(900/(T+273))*u2*(es-ea)] / [Delta + gamma*(1+0.34*u2)]
ETc = Kc * ET0
TAW = 1000*(theta_FC-theta_WP)*Zr
p = clip(p_table + 0.04*(5-ETc), 0.1, 0.8)
RAW = p * TAW
Dr = clip(1000*(theta_FC-theta_current)*Zr, 0, TAW)
theta_crit = theta_FC - p*(theta_FC-theta_WP)
Trigger if Dr >= RAW
I_net = max(0, Dr-P_eff) when triggered; otherwise 0
I_gross = I_net / E_a
```
Daily tests use G = 0.

### L1-GOLDEN-001 — Normal non-triggering case

**Inputs**

| Input | Value |
|---|---:|
| Air temperature (°C) | 30 |
| Relative humidity (%) | 50 |
| Wind at 2m (m/s) | 2 |
| Net radiation (MJ/m²/day) | 18 |
| Crop coefficient | 1.0 |
| Fixture p_table | 0.55 |
| Field capacity (m³/m³) | 0.3 |
| Wilting point (m³/m³) | 0.15 |
| Root depth (m) | 0.6 |
| Current soil moisture (m³/m³) | 0.24 |
| Effective rainfall (mm) | 0 |
| Application efficiency | 0.9 |
| Elevation (m) | 900 |

**Expected outputs**

| Output | Expected |
|---|---:|
| ET₀ (mm/day) | 7.390559 |
| ETc (mm/day) | 7.390559 |
| TAW (mm) | 90.000000 |
| Adjusted p | 0.454378 |
| RAW (mm) | 40.893987 |
| Root-zone depletion (mm) | 36.000000 |
| Critical moisture θcrit | 0.231843 |
| Irrigation trigger | False |
| Net irrigation (mm) | 0 |
| Gross irrigation (mm) | 0 |

Acceptance: values must match within the configured numeric tolerance.

### L1-GOLDEN-002 — High-ET dry case that must trigger irrigation

**Inputs**

| Input | Value |
|---|---:|
| Air temperature (°C) | 35 |
| Relative humidity (%) | 40 |
| Wind at 2m (m/s) | 3 |
| Net radiation (MJ/m²/day) | 22 |
| Crop coefficient | 1.15 |
| Fixture p_table | 0.5 |
| Field capacity (m³/m³) | 0.32 |
| Wilting point (m³/m³) | 0.16 |
| Root depth (m) | 0.6 |
| Current soil moisture (m³/m³) | 0.2 |
| Effective rainfall (mm) | 0 |
| Application efficiency | 0.9 |
| Elevation (m) | 900 |

**Expected outputs**

| Output | Expected |
|---|---:|
| ET₀ (mm/day) | 10.576476 |
| ETc (mm/day) | 12.162947 |
| TAW (mm) | 96.000000 |
| Adjusted p | 0.213482 |
| RAW (mm) | 20.494283 |
| Root-zone depletion (mm) | 72.000000 |
| Critical moisture θcrit | 0.285843 |
| Irrigation trigger | True |
| Net irrigation (mm) | 72.000000 |
| Gross irrigation (mm) | 80.000000 |

Acceptance: values must match within the configured numeric tolerance.

### L1-GOLDEN-003 — Rain-present case; no trigger because current depletion is below RAW

**Inputs**

| Input | Value |
|---|---:|
| Air temperature (°C) | 28 |
| Relative humidity (%) | 70 |
| Wind at 2m (m/s) | 1.5 |
| Net radiation (MJ/m²/day) | 14 |
| Crop coefficient | 0.85 |
| Fixture p_table | 0.55 |
| Field capacity (m³/m³) | 0.28 |
| Wilting point (m³/m³) | 0.14 |
| Root depth (m) | 0.5 |
| Current soil moisture (m³/m³) | 0.25 |
| Effective rainfall (mm) | 5 |
| Application efficiency | 0.9 |
| Elevation (m) | 900 |

**Expected outputs**

| Output | Expected |
|---|---:|
| ET₀ (mm/day) | 5.023799 |
| ETc (mm/day) | 4.270229 |
| TAW (mm) | 70.000000 |
| Adjusted p | 0.579191 |
| RAW (mm) | 40.543360 |
| Root-zone depletion (mm) | 15.000000 |
| Critical moisture θcrit | 0.198913 |
| Irrigation trigger | False |
| Net irrigation (mm) | 0 |
| Gross irrigation (mm) | 0 |

Acceptance: values must match within the configured numeric tolerance.

### L1-GOLDEN-004 — Boundary: depletion exactly equals RAW; trigger must be TRUE

**Inputs**

| Input | Value |
|---|---:|
| Air temperature (°C) | 30 |
| Relative humidity (%) | 50 |
| Wind at 2m (m/s) | 2 |
| Net radiation (MJ/m²/day) | 18 |
| Crop coefficient | 1.0 |
| Fixture p_table | 0.55 |
| Field capacity (m³/m³) | 0.3 |
| Wilting point (m³/m³) | 0.15 |
| Root depth (m) | 0.6 |
| Current soil moisture (m³/m³) | 0.23184335434077194 |
| Effective rainfall (mm) | 0 |
| Application efficiency | 0.9 |
| Elevation (m) | 900 |

**Expected outputs**

| Output | Expected |
|---|---:|
| ET₀ (mm/day) | 7.390559 |
| ETc (mm/day) | 7.390559 |
| TAW (mm) | 90.000000 |
| Adjusted p | 0.454378 |
| RAW (mm) | 40.893987 |
| Root-zone depletion (mm) | 40.893987 |
| Critical moisture θcrit | 0.231843 |
| Irrigation trigger | True |
| Net irrigation (mm) | 40.893987 |
| Gross irrigation (mm) | 45.437764 |

Acceptance: values must match within the configured numeric tolerance.

### L1-GOLDEN-005 — High-ET case to verify p lower-bound clipping at 0.10

**Inputs**

| Input | Value |
|---|---:|
| Air temperature (°C) | 40 |
| Relative humidity (%) | 20 |
| Wind at 2m (m/s) | 4 |
| Net radiation (MJ/m²/day) | 25 |
| Crop coefficient | 1.3 |
| Fixture p_table | 0.55 |
| Field capacity (m³/m³) | 0.3 |
| Wilting point (m³/m³) | 0.15 |
| Root depth (m) | 0.6 |
| Current soil moisture (m³/m³) | 0.2 |
| Effective rainfall (mm) | 0 |
| Application efficiency | 0.9 |
| Elevation (m) | 900 |

**Expected outputs**

| Output | Expected |
|---|---:|
| ET₀ (mm/day) | 15.149490 |
| ETc (mm/day) | 19.694338 |
| TAW (mm) | 90.000000 |
| Adjusted p | 0.100000 |
| RAW (mm) | 9.000000 |
| Root-zone depletion (mm) | 60.000000 |
| Critical moisture θcrit | 0.285000 |
| Irrigation trigger | True |
| Net irrigation (mm) | 60.000000 |
| Gross irrigation (mm) | 66.666667 |

Acceptance: values must match within the configured numeric tolerance.

## Recommended test tolerances
- Floating-point intermediates: use approximately `1e-6` absolute tolerance where feasible.
- ET₀/ETc/TAW/RAW/depletion: use a documented engineering tolerance such as `1e-4` mm for deterministic fixture comparison.
- Trigger booleans: exact match.
- Stored values must not be rounded merely for UI display.

## Required automated tests
1. Execute all five golden cases on every Layer 1 change.
2. Test moisture below WP and above FC clamping.
3. Test p lower and upper clipping.
4. Test `Dr == RAW` triggers irrigation.
5. Test non-trigger produces zero irrigation.
6. Test `1 mm × 1 m² = 1 L`.
7. Test valve runtime `t = V/Q`.
8. Test negative water requirement is clamped/rejected according to the Layer 1 spec.

## Agent rule
> Do not alter expected values to make failing code pass. Investigate equations, units, configuration and implementation first. Any change to the mathematical specification requires explicit approval.