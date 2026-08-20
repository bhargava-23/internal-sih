# AquaSence AI V1 — Judge Demo Sequence

## Purpose

This document defines the exact live demonstration sequence for the simulation prototype.

The demo must prove the complete operational loop:

```text
INPUT
  ↓
UNDERSTAND
  ↓
PREDICT
  ↓
DECIDE
  ↓
ACT
  ↓
VERIFY
  ↓
LEARN
```

The demo uses realistic simulated field inputs. The computational pipeline is real.

---

# 1. Demo rules

1. Do not present simulated observations as real field measurements.
2. Do not claim production or field validation.
3. Do not explain every implementation detail unless a judge asks.
4. Always show the cause → computation → decision → response chain.
5. Use the same five canonical scenarios defined in `scenario_fixtures.json`.
6. Prefer a short live flow over clicking through many screens.
7. If a live service fails, use the approved simulation fallback and explicitly indicate degraded/forecast mode.

---

# 2. Demo duration

## Target

**6–8 minutes**

Suggested allocation:

| Segment | Time |
|---|---:|
| Opening / problem | 30 sec |
| System overview | 45 sec |
| Scenario 1 — healthy | 30 sec |
| Scenario 2 — drying / irrigation | 90 sec |
| Scenario 3 — rain forecast | 60 sec |
| Scenario 4 — high ET | 45 sec |
| Scenario 5 — delivery anomaly | 60 sec |
| Feedback / learning | 45 sec |
| Closing | 30 sec |

---

# 3. Opening statement

Use a concise opening:

> “AquaSence AI is a closed-loop precision irrigation system. For this prototype, the physical sensor and actuator layer is simulated with realistic field conditions, while the actual agronomic, forecasting, decision and feedback pipeline runs live.”

Then:

> “The key difference is that we are not simply asking whether the soil is dry. The system estimates agricultural water demand, forecasts future root-zone conditions, decides whether irrigation is needed, determines the required water, simulates the valve response, and verifies the outcome.”

---

# 4. Screen / dashboard state before starting

The landing dashboard should visibly show:

### Current field cards

- Root-zone moisture
- Temperature
- Relative humidity
- Wind
- Rainfall
- ET₀
- ETc
- Water requirement
- Valve state
- Flow rate
- Pressure
- Forecast next 24h
- Predicted root-zone moisture

### Main graphs

1. Root-zone moisture vs FC / RAW / WP
2. Actual vs predicted moisture
3. ET₀ / ETc
4. Rainfall + forecast
5. Flow / pressure
6. Irrigation timeline

---

# 5. Scenario 1 — HEALTHY ROOT ZONE

## Action

Select:

**Healthy Root Zone**

## Expected state

- Moisture is within the acceptable region.
- ETc is moderate.
- No irrigation trigger.
- Valve remains closed.

## Judge narration

> “The system starts in a healthy condition. The root zone currently has sufficient available water, so the agronomic engine does not trigger irrigation.”

### Show

- Root-zone moisture card
- RAW threshold
- Valve = CLOSED
- Water requirement = 0 / no current irrigation
- Moisture graph

### What this proves

The system does **not irrigate simply because automation is enabled**.

---

# 6. Scenario 2 — DRYING FIELD / IRRIGATION REQUIRED

## Action

Select:

**Drying Field**

Or increase:

- temperature
- evaporative demand
- moisture depletion
- zero rainfall

## Expected flow

```text
Current field state
      ↓
Layer 1
      ↓
ET₀ / ETc increase
      ↓
root-zone depletion increases
      ↓
physics-forward +24h forecast
      ↓
XGBoost residual correction
      ↓
future moisture approaches / crosses RAW threshold
      ↓
irrigation decision
      ↓
water requirement
      ↓
simulated valve OPEN
```

## Judge narration

> “Now we create a drying condition. The current state is combined with the next 24 hours of forecast weather. Layer 1 gives us the physics-based trajectory, while XGBoost learns the field-specific residual correction.”

Then:

> “The system predicts that the root zone will move beyond the acceptable depletion threshold, so irrigation is initiated.”

### Show live

- ET₀ rising
- ETc
- current depletion
- RAW
- physics forecast
- XGBoost correction
- final predicted moisture
- calculated water requirement
- valve = OPEN
- flow rate
- pressure

### Strong UI moment

Display:

**Irrigation Required**

Then:

**Required Volume: XX L**

Then:

**Valve Runtime: XX min**

---

# 7. Scenario 2 — SIMULATED IRRIGATION RESPONSE

Once the valve opens, do not instantly jump to the final state.

Show a short timeline:

```text
Valve OPEN
   ↓
Flow detected
   ↓
Water delivered
   ↓
Root-zone moisture rises
   ↓
Target reached
   ↓
Valve CLOSE
```

## Judge narration

> “We also verify the action. A valve command alone does not prove that the correct amount of water was delivered. The simulation therefore produces flow, pressure and soil-response signals.”

### Show

- valve status
- flow rate
- pressure
- delivered volume
- soil-moisture response

Then:

**Target reached → Valve CLOSED**

---

# 8. Scenario 3 — RAIN INCOMING

## Action

Select:

**Rain Forecast / Irrigation Deferred**

Set a meaningful 24-hour precipitation forecast.

Example:

**Forecast rainfall = 18 mm**

## Expected behavior

The physics-forward prediction should account for expected rainfall.

The system should avoid unnecessary immediate irrigation when the forecast indicates substantial useful rainfall and the field state remains acceptable.

## Judge narration

> “This scenario is important because a purely reactive moisture-threshold system cannot see tomorrow's weather. Our system consumes the actual 24-hour forecast and incorporates it into both the physics-forward prediction and the XGBoost feature set.”

Then show:

```text
Forecast Rainfall
       ↓
lower predicted depletion
       ↓
lower future irrigation need
       ↓
IRRIGATION DEFERRED
```

### Key cards

- forecast rainfall
- predicted 24h moisture
- RAW threshold
- irrigation state = DEFERRED / NOT REQUIRED

---

# 9. Scenario 4 — HIGH ET / HEAT

## Action

Select:

**High ET / Heat Stress**

Use:

- high temperature
- low humidity
- strong radiation
- no rainfall

## Expected behavior

```text
Temperature ↑
Humidity ↓
Radiation ↑
      ↓
ET₀ ↑
      ↓
ETc ↑
      ↓
faster depletion
      ↓
higher irrigation demand
```

## Judge narration

> “Here we change the atmospheric demand rather than directly changing soil moisture. The system reacts through ET₀ and ETc, demonstrating that irrigation demand is not determined by a single moisture threshold.”

### Show graph

**ET₀ / ETc over time**

And:

**Predicted root-zone moisture decline**

---

# 10. Scenario 5 — DELIVERY ANOMALY

## Action

Select:

**Valve / Hydraulic Delivery Anomaly**

Command:

- flow = 5 L/min

Simulate:

- actual flow = 2.2 L/min

## Expected behavior

```text
Commanded delivery
       ↓
Actual flow
       ↓
mismatch detected
       ↓
delivery anomaly
       ↓
alert
```

## Judge narration

> “This is why the system is closed-loop. If we command a valve to deliver a certain amount but the measured flow is substantially lower, the system detects the deviation instead of assuming success.”

### Show

**Expected Flow:** 5.0 L/min  
**Actual Flow:** 2.2 L/min

Alert:

**Delivery deviation detected**

---

# 11. Feedback / learning demonstration

Return to the prediction/metrics section.

Show:

- number of predictions
- MAE
- RMSE
- bias
- recent residual error
- prediction history
- retraining status

## Judge narration

> “Every prediction is logged against the eventual observed outcome. We track error and bias over time. When enough real-field observations accumulate, the residual model can be retrained offline and validated chronologically before it is used again.”

Important wording:

> “The current prototype demonstrates the mechanism and simulation validation. These metrics should not be presented as field-validation accuracy.”

---

# 12. Required graphs for the demo

## Graph 1 — Root-zone moisture

### X-axis
Time

### Y-axis
Volumetric soil moisture

### Required lines

- actual / simulated moisture
- predicted +24h moisture
- FC
- RAW trigger level
- WP

### Main purpose

Demonstrates:

**state + forecast + irrigation threshold + response**

---

## Graph 2 — ET₀ and ETc

Show:

- ET₀
- ETc

### Purpose

Demonstrates:

**weather → crop demand**

---

## Graph 3 — Rainfall + forecast

Show:

- historical rainfall
- next-24h forecast rainfall

### Purpose

Demonstrates:

**forecast awareness**

---

## Graph 4 — Physics vs XGBoost vs actual

Three series:

- physics forecast
- corrected XGBoost forecast
- actual / simulated future moisture

### Purpose

This is the **ML proof graph**.

The visual should show whether the residual correction moves the physics forecast closer to the actual trajectory.

---

## Graph 5 — Residual error

Plot:

```text
actual - physics prediction
```

and optionally:

```text
actual - corrected prediction
```

### Purpose

Demonstrates what XGBoost is learning.

---

## Graph 6 — Flow and pressure

During irrigation show:

- commanded/expected flow
- measured/simulated actual flow
- pressure

### Purpose

Demonstrates physical delivery verification.

---

## Graph 7 — Prediction metrics over time

Show rolling or cumulative:

- MAE
- RMSE
- bias
- R² if available and meaningful

### Important

Do not invent an improving curve.

The graph must come from actual simulation/training output.

---

# 13. KPI cards

Minimum top-level cards:

| Card | Value |
|---|---|
| Root-Zone Moisture | XX % |
| Predicted +24h Moisture | XX % |
| ET₀ | XX mm/day |
| ETc | XX mm/day |
| Water Requirement | XX L |
| Valve | OPEN/CLOSED |
| Flow | XX L/min |
| Pressure | XX bar |

Second row:

| Card | Value |
|---|---|
| RAW | XX mm |
| Current Depletion | XX mm |
| Forecast Rain | XX mm |
| Physics Forecast | XX |
| XGBoost Correction | ±XX |
| Final Forecast | XX |
| Prediction MAE | XX |
| Bias | ±XX |

---

# 14. Important model explanation panel

The dashboard should have a compact **Decision Trace**.

Example:

```text
WHY?

Root-zone moisture          21.4%
Current depletion            61 mm
RAW threshold                56 mm
ETc                           6.2 mm/day
Forecast rainfall             0 mm
Physics forecast              20.8%
XGBoost correction            +0.7%
Final +24h forecast           20.1%
Decision                      IRRIGATE
Required water               142 L
```

This is extremely valuable during judging because it lets you answer:

> “Why did the system decide to irrigate?”

without opening the code.

---

# 15. If the judge asks “Where does AI actually come in?”

Answer:

> “The agronomic engine provides the physics-based baseline. The AI layer is XGBoost, which learns the residual between the physics forecast and observed field behavior. It uses current history plus the next 24 hours of weather forecast to improve the future root-zone prediction.”

---

# 16. If the judge asks “Why not just use FAO-56?”

Answer:

> “FAO-56 provides the physical baseline, but it relies on generalized crop, soil and environmental assumptions. Our residual model is intended to learn systematic local differences between that baseline and observed field behavior.”

---

# 17. If the judge asks “Is this trained on real farm data?”

Answer honestly:

> “For this prototype, the field layer is simulated and the training/validation pipeline uses reproducible simulation/public-weather inputs. We are not presenting those results as field validation. The architecture is designed so the simulated target is replaced by real root-zone measurements once the physical prototype begins collecting data.”

---

# 18. If the judge asks “Why XGBoost?”

Answer:

> “Our current Layer-2 problem is structured, heterogeneous sensor and weather data with engineered temporal features. XGBoost gives us a strong nonlinear regression model with lower data and compute requirements than a deep sequence model, while remaining interpretable enough for a prototype. LSTM remains a future benchmark when sufficient real sequential data is available.”

---

# 19. If the judge asks “How does it learn?”

Answer:

> “Every prediction is logged against the eventual observed outcome. We calculate error and bias over time and periodically retrain the residual model offline using accumulated field observations, validating chronologically before using the new model.”

---

# 20. If the judge asks “What happens if the AI is wrong?”

Answer:

> “The AI does not directly control the valve. The deterministic agronomic and safety logic remains the authority for irrigation action. The model provides the future-state forecast and local correction.”

---

# 21. Demo failure fallback

If Open-Meteo is unavailable:

1. switch to simulation forecast mode;
2. visibly indicate forecast source is simulated;
3. continue using the deterministic simulation seed;
4. do not silently substitute stale data;
5. continue the demonstration.

If XGBoost model is unavailable:

1. show physics-only forecast;
2. display model state as `ML UNAVAILABLE`;
3. continue the demo without claiming AI correction occurred.

If the simulation engine errors:

1. load the last known fixture state;
2. display `SIMULATION ERROR / SAFE STATE`;
3. do not fake a successful outcome.

---

# 22. Final demo order

Use this exact order:

```text
1. OPEN DASHBOARD
2. HEALTHY FIELD
3. DRYING FIELD
4. SHOW LAYER 1 + PHYSICS + XGBOOST
5. SHOW WATER REQUIREMENT
6. OPEN SIMULATED VALVE
7. SHOW FLOW / PRESSURE / MOISTURE RESPONSE
8. RAIN FORECAST SCENARIO
9. HIGH ET SCENARIO
10. DELIVERY ANOMALY
11. SHOW ERROR / BIAS LOGGING
12. SHOW RETRAINING PIPELINE / MODEL METRICS
13. CLOSE WITH SYSTEM ARCHITECTURE
```

---

# 23. Closing statement

> “AquaSence is not a dashboard that predicts irrigation. It is a closed-loop decision system: it understands field conditions, estimates agricultural demand, forecasts future root-zone state, determines the required action, verifies the physical response, and records the outcome for future model improvement.”

---

# 24. V1 demo success criteria

The demo is successful if a judge can visibly verify:

- inputs change;
- Layer 1 calculations update;
- forecast weather affects prediction;
- XGBoost residual correction runs;
- future moisture is predicted;
- irrigation requirement is calculated;
- simulated valve changes state;
- flow/pressure respond;
- soil moisture changes;
- anomaly detection works;
- prediction outcomes are logged;
- metrics are computed;
- no simulated result is misrepresented as field validation.

---

# 25. Final demo principle

**Do not optimize for maximum screen count. Optimize for maximum cause-and-effect clarity.**

The strongest demo is the one where the judge changes one field condition and immediately sees:

```text
CHANGE
  ↓
AGRONOMIC EFFECT
  ↓
PREDICTIVE EFFECT
  ↓
IRRIGATION DECISION
  ↓
VALVE RESPONSE
  ↓
FIELD RESPONSE
  ↓
MEASURED OUTCOME
```

That is the product.
