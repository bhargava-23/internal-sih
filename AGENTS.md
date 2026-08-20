# AquaSence AI — AGENTS.md

> **Purpose:** This file is the operating contract for AI coding agents working on the AquaSence AI repository.
>
> **Primary agent:** Google Antigravity Agent Mode using Claude Sonnet 4.6.
>
> **Rule:** The agent must implement the approved system. It must not redesign, simplify, expand, or reinterpret the architecture unless the user explicitly authorizes a change.

---

## 1. PROJECT IDENTITY

**Project:** AquaSence AI  
**Team:** Team Rocket  
**Program:** Smart India Hackathon 2026  
**Problem Statement ID:** SIH260220

### Core problem

Automatic regulation of irrigation valves based on soil-moisture availability in the crop root zone, using artificial intelligence, in piped and micro-irrigation networks.

### V1 prototype mode

The first prototype is a **simulation-driven prototype**.

Physical field sensors, pumps, valves, flow meters, pressure sensors, and other hardware may be represented by realistic simulated inputs and simulated field responses.

The downstream computational pipeline must remain real:

```text
Simulated / External Inputs
        ↓
Layer 1 Agronomic Engine
        ↓
Physics Forward Forecast
        ↓
Layer 2 XGBoost Residual Model
        ↓
Decision Engine
        ↓
Simulated Actuation
        ↓
Simulated Field Response
        ↓
Feedback Logging
        ↓
Offline Retraining
```

The prototype must not pretend simulated observations are real field observations.

---

# 2. SOURCE-OF-TRUTH HIERARCHY

The repository contains multiple specifications. They have different authority.

## Level 1 — Global Product Authority

### `01_MASTER_PRD`
**Controls:**
- SIH problem statement
- product scope
- product objectives
- system purpose
- high-level requirements
- non-negotiable product behavior

## Level 2 — V1 Execution Authority

### `02_SIMULATION_PROTOTYPE_SPEC`
**Controls:**
- what the prototype actually implements
- simulation inputs
- simulated field behavior
- demo scenarios
- visible outputs
- judge-facing prototype behavior
- V1 scope limitations

If the production architecture mentions physical hardware but the simulation specification says to simulate that hardware for V1, **simulate it**. Do not add physical hardware requirements to the V1 software build.

## Level 3 — Technical Architecture Authority

### `03_TRD`
**Controls:**
- frontend/backend technology choices
- runtime architecture
- packages
- repository structure
- deployment/runtime assumptions
- technology constraints

## Level 4 — Backend Contract Authority

### `04_BACKEND_SCHEMA`
**Controls:**
- database schema
- API contracts
- request/response models
- WebSocket events
- backend data relationships
- persistence rules

## Level 5 — Agronomic Domain Authority

### `05_LAYER1_SPEC`
**Controls:**
- FAO-compatible calculations
- ET₀
- Kc
- ETc
- TAW
- p
- RAW
- root-zone depletion
- water balance
- irrigation requirement
- valve runtime calculations

Do not invent or replace agronomic equations.

## Level 6 — ML Domain Authority

### `06_LAYER2_SPEC`
**Controls:**
- XGBoost residual-model formulation
- 24-hour target
- feature contract
- forecast-weather dependency
- physics-forward baseline
- residual definition
- train/validation/test strategy
- evaluation metrics

Do not change the ML target or architecture because a simpler implementation appears convenient.

## Level 7 — Feedback Authority

### `07_FEEDBACK_SPEC`
**Controls:**
- sensor QC
- prediction/outcome logging
- error and bias calculation
- periodic offline retraining
- V1 feedback scope

Do not introduce production MLOps systems into V1.

## Level 8 — Product Interaction Authority

### `08_APP_FLOW`
**Controls:**
- screens
- navigation
- interactions
- states
- workflows
- user actions

## Level 9 — Visual UX Authority

### `09_UIUX_BRIEF`
**Controls:**
- visual design
- layout
- typography
- colors
- component styling
- responsive behavior

## Level 10 — Execution Authority

### `10_IMPLEMENTATION_PLAN`
**Controls:**
- task order
- task boundaries
- agent workflow
- acceptance criteria
- definition of done

The implementation plan tells the agent **HOW TO EXECUTE**. It must not override domain specifications that define **WHAT TO BUILD**.

---

# 3. CORE OPERATING PRINCIPLE

## Build the minimum complete system.

The goal is not to maximize technologies, features, abstractions, APIs, or architectural sophistication.

The goal is:

> **A reliable end-to-end prototype that demonstrates the complete AquaSence decision loop.**

Every implementation decision must be judged against:

1. Does it help the prototype work?
2. Does it improve correctness?
3. Does it improve demonstrability?
4. Does it preserve the locked architecture?
5. Is it necessary now?

If the answer is "no" to all of these, **do not build it**.

---

# 4. DO NOT EXPAND THE ARCHITECTURE

The following are explicitly **out of V1 scope unless the user re-authorizes them**:

- microservices
- Kafka
- Redis
- Celery
- Kubernetes
- event-bus frameworks
- unnecessary message brokers for the simulation runtime
- large UI frameworks
- Redux unless genuinely necessary
- separate ML serving infrastructure
- online model retraining
- Kalman/EnKF state assimilation
- ADWIN drift detection
- automated nonlinear agronomic-parameter optimization
- champion/challenger production deployment
- conformal prediction / uncertainty infrastructure
- satellite-data ingestion pipelines
- IMD ingestion pipelines
- NOAA ingestion pipelines
- direct Copernicus/ERA5-Land ingestion pipelines
- GPM/IMERG ingestion pipelines
- NISAR ingestion pipelines
- SMAP ingestion pipelines
- SoilGrids ingestion pipelines

### V1 external data dependency

Use **Open-Meteo** as the only external weather/data service required by the prototype.

Use the existing FAO/static agronomic configuration for soil parameters and crop information.

---

# 5. V1 ARCHITECTURE — DO NOT CHANGE

The canonical flow is:

```text
                 FIELD / SIMULATOR
                        │
                        ▼
              SENSOR / INPUT VALIDATION
                        │
                        ▼
                 ┌──────────────┐
                 │   LAYER 1    │
                 │ AGRONOMIC    │
                 │ ENGINE       │
                 └──────┬───────┘
                        │
             Current state + forecast weather
                        │
                        ▼
              PHYSICS FORWARD RUN
                        │
                        ▼
               24h PHYSICS FORECAST
                        │
                        ▼
                 XGBOOST RESIDUAL
                     MODEL
                        │
                        ▼
             CORRECTED 24h FORECAST
                        │
                        ▼
                 DECISION ENGINE
                        │
                        ▼
                 WATER REQUIREMENT
                        │
                        ▼
                 SIMULATED VALVE
                        │
                        ▼
               SIMULATED FIELD RESPONSE
                        │
                        ▼
                   FEEDBACK LOG
                        │
                        ▼
              OFFLINE RETRAINING
```

The model does **not** directly control the valve.

The agronomic/decision layer remains the authority for irrigation action.

---

# 6. LAYER 1 RULES

Layer 1 is deterministic.

It is not an ML model.

Core sequence:

```text
Weather
  ↓
ET₀
  ↓
Kc
  ↓
ETc
  ↓
TAW / p / RAW
  ↓
Current root-zone water status
  ↓
Water balance
  ↓
Irrigation trigger
  ↓
Net requirement
  ↓
Gross requirement
  ↓
Water volume
  ↓
Valve runtime
```

### Required discipline

- Keep equations explicit.
- Keep units explicit.
- Keep crop and soil parameters configurable.
- Never silently substitute a different formula.
- Do not "simplify" agronomic calculations for convenience.
- Keep Layer 1 independently testable.

---

# 7. LAYER 2 RULES

## Primary model

**XGBoost regression**

## Target

24-hour-ahead root-zone moisture residual:

```text
residual(t+24)
=
actual_root_zone_moisture(t+24)
-
physics_forecast_root_zone_moisture(t+24)
```

## Final forecast

```text
final_forecast
=
physics_forecast
+
xgboost_residual_prediction
```

## Why the residual model exists

Layer 1 provides a physics/agronomy-based baseline.

XGBoost learns the systematic field-specific error that the generalized physical model cannot capture.

## Mandatory forecast input

Layer 2 must use future weather information available at prediction time.

At minimum, use forecast variables appropriate to the Open-Meteo contract, such as:
- forecast precipitation
- forecast temperature
- forecast humidity
- forecast wind
- forecast radiation / ET₀ where available

Do not build a "24-hour forecast" model that sees only past data if forecast data is available.

---

# 8. XGBOOST DATA RULES

The agent must build the dataset programmatically.

The user must not be required to manually construct thousands of CSV rows.

## The data pipeline must:

1. retrieve historical weather data;
2. validate and normalize timestamps;
3. compute Layer 1 derived features;
4. generate realistic field/simulation trajectories;
5. create a physics-forward +24h prediction;
6. create structured, feature-correlated synthetic deviations for Stage 1 simulation;
7. calculate residual targets;
8. engineer lag/rolling/forecast features;
9. perform chronological train/validation/test splitting;
10. export a canonical training dataset;
11. train/evaluate XGBoost;
12. save model metadata and metrics.

### Synthetic data rule

Do **not** create residual targets using pure random noise alone.

Synthetic deviations must contain structured relationships that depend on features the model can observe, for example:
- crop stage
- temperature conditions
- soil characteristics
- forecast error
- sensor bias/drift assumptions, if explicitly modeled

The simulation must clearly label synthetic data as synthetic.

Never present synthetic accuracy as real-world field accuracy.

---

# 9. LEAKAGE RULES

At prediction time `t`, features may contain information known at or before `t`, plus explicitly available forecasts for `t → t+24h`.

Never use:

- future observed rainfall
- future observed soil moisture
- future actual irrigation
- future actual flow
- future actual pressure
- future values that would not have been available at time `t`

unless those values are explicitly a forecast product.

The train/validation/test split must be chronological.

---

# 10. FEEDBACK V1 RULES

V1 feedback is intentionally simple.

Implement:

```text
prediction
↓
actual outcome
↓
error
↓
bias
↓
logging
↓
periodic offline retraining
```

Do not implement:
- online retraining
- Kalman filtering
- EnKF
- ADWIN
- automated parameter optimization
- production model orchestration

### Retraining

When enough labelled real-field outcomes exist:

1. append data;
2. retrain offline;
3. validate chronologically;
4. compare metrics against the previous model;
5. replace only if the candidate improves on the agreed validation criteria.

---

# 11. FRONTEND RULES

Frontend:

**React + TypeScript + Vite**

Use the existing UI/UX specification.

Priorities:

1. clear real-time status
2. root-zone moisture
3. ET/ETc
4. predicted 24h moisture
5. irrigation requirement
6. valve state
7. flow/pressure
8. rainfall/forecast
9. prediction error
10. scenario controls

The dashboard is a **decision explanation interface**, not a decorative analytics wall.

Do not add unnecessary dashboards.

---

# 12. BACKEND RULES

Backend:

**FastAPI + Python**

Responsibilities:

- simulation state
- weather ingestion
- Layer 1 execution
- Layer 2 model execution
- decision execution
- persistence
- WebSocket events
- feedback logging

Keep the backend modular by responsibility.

Do not create microservices.

---

# 13. DATABASE RULES

Database:

**SQLite + SQLAlchemy**

Maintain traceability between:

```text
sensor/input
   ↓
Layer 1 calculation
   ↓
physics forecast
   ↓
XGBoost prediction
   ↓
final forecast
   ↓
decision
   ↓
actuation
   ↓
actual response
   ↓
error
```

A judge/developer must be able to inspect a prediction and understand:
- what inputs produced it;
- what Layer 1 predicted;
- what XGBoost corrected;
- what decision was made;
- what happened afterward.

---

# 14. SIMULATION RULES

The simulator is not a fake UI.

It is a deterministic/reproducible state engine.

It must simulate:

- soil moisture evolution
- rainfall response
- evapotranspiration/depletion
- irrigation response
- flow
- pressure
- valve state
- sensor readings
- realistic perturbations

### Reproducibility

Every scenario must have:
- a seed;
- known starting conditions;
- controlled parameter values;
- reproducible output.

A simulation must be rerunnable with the same inputs.

---

# 15. DEMO SCENARIOS — REQUIRED

At minimum implement:

### Scenario 1 — Healthy

Root zone sufficiently wet.

Expected:
- no irrigation;
- system continues monitoring.

### Scenario 2 — Drying

Low moisture + high evaporative demand.

Expected:
- Layer 1 identifies/approaches trigger;
- XGBoost predicts future depletion;
- water requirement calculated;
- valve opens in simulation.

### Scenario 3 — Rain incoming

Moderately dry state + forecast rainfall.

Expected:
- forecast affects physics-forward prediction;
- irrigation is deferred/reduced when appropriate.

### Scenario 4 — High ET

High temperature + low humidity + strong radiation.

Expected:
- ET₀/ETc increase;
- future moisture decline increases;
- irrigation demand changes.

### Scenario 5 — Delivery anomaly

Valve command is issued but simulated flow is lower than expected.

Expected:
- actual delivery differs;
- deviation is logged;
- alert is shown.

---

# 16. ENGINEERING STYLE

Claude Sonnet 4.6 must prefer:

- small modules
- typed interfaces
- explicit data models
- predictable naming
- straightforward control flow
- pure functions for domain calculations
- testable functions
- minimal abstractions
- comments explaining WHY, not WHAT

Avoid:
- clever metaprogramming
- over-generalized factories
- deep inheritance trees
- unnecessary dependency injection
- giant files
- magic globals
- duplicated business logic
- hidden side effects

---

# 17. IMPLEMENTATION BEHAVIOR FOR CLAUDE SONNET 4.6

Before changing code:

1. inspect repository;
2. inspect existing related files;
3. identify source-of-truth document;
4. explain intended file changes;
5. implement the smallest coherent change;
6. run tests/type checks/lint;
7. inspect failures;
8. fix only relevant failures;
9. summarize changed files and verification.

Do not rewrite unrelated code.

Do not refactor unrelated modules while completing a task.

Do not introduce new dependencies unless:
- they are already approved by the TRD; or
- the user explicitly approves them.

---

# 18. AGENT TASK DISCIPLINE

Every task must have:

- task ID
- objective
- scope
- files expected to change
- dependencies
- acceptance criteria
- verification command

The agent must complete one bounded task at a time unless explicit parallel work is requested.

If a task reveals an architectural conflict:

**STOP and report it.**

Do not silently redesign the architecture.

---

# 19. BEFORE IMPLEMENTING A FEATURE

Ask:

### Is this already specified?

If yes:
- follow the specification.

If no:
- inspect neighboring specifications;
- if still unclear, ask before inventing behavior.

### Is this necessary for V1?

If no:
- do not implement.

### Is this a new dependency?

If yes:
- do not add it without approval unless it is already explicitly listed in the TRD.

---

# 20. TESTING REQUIREMENTS

Every computational domain should have deterministic unit tests.

Minimum test categories:

## Layer 1

- ET₀ calculation
- Kc selection
- ETc
- TAW
- RAW
- current depletion
- trigger decision
- irrigation depth
- litre conversion
- valve runtime

## Layer 2

- feature generation
- residual target construction
- temporal split
- leakage checks
- model training
- model prediction
- metric calculation

## Simulation

- rainfall
- irrigation
- drying
- valve state
- flow anomaly
- pressure anomaly
- deterministic seed behavior

## API

- valid request
- invalid request
- missing data
- simulation start/stop
- scenario selection
- prediction endpoint
- WebSocket event flow

## Frontend

- main dashboard loads
- simulation controls work
- live state updates
- graphs update
- alerts render
- scenario switching works

---

# 21. DATA QUALITY RULES

Every data adapter must define:

- source timestamp;
- timezone;
- units;
- missing-value behavior;
- bounds;
- validation;
- normalization;
- provenance.

Never silently guess units.

Never silently coerce invalid numbers into valid ones.

If data is unavailable:
- return an explicit degraded state;
- log the reason;
- do not silently use stale data.

---

# 22. MODEL CLAIM RULES

Never write or display claims such as:

- "90% accurate"
- "production ready"
- "field validated"
- "saves X% water"
- "improves yield by X%"

unless that claim is supported by actual evaluated evidence.

For simulated data, label metrics:

**Simulation Validation**

For public-data experiments, label metrics:

**Public/Historical Validation**

For real field data, label metrics:

**Field Validation**

Do not mix these categories.

---

# 23. SAFETY RULES

The simulated decision engine may open/close simulated valves.

However:

- ML predictions must not bypass deterministic decision logic;
- impossible states must be rejected;
- negative water requirements are invalid;
- impossible moisture values are invalid;
- valve runtime must be bounded;
- flow/pressure violations must be handled;
- missing critical inputs must produce a safe state.

---

# 24. UI/UX RULES

Follow the approved design language:

- warm sand/bone-white canvas
- charcoal text
- thin 1px borders
- minimal corner radius
- no unnecessary shadows
- editorial typography
- compact data cards
- clear status hierarchy
- functional graphs
- restrained color use

Do not introduce an unrelated visual system.

---

# 25. REPOSITORY DISCIPLINE

Expected major directories:

```text
/
├── AGENTS.md
├── docs/
├── backend/
├── frontend/
├── simulation/
├── agronomy/
├── ml/
├── data/
├── tests/
└── scripts/
```

Do not create additional top-level directories without reason.

Keep generated datasets/model files separate from source code.

---

# 26. MODEL ARTIFACTS

Every trained model must have:

- model file
- training timestamp
- dataset/version identifier
- feature list
- target definition
- train/validation/test ranges
- metrics
- training configuration

The application must know which model version it is using.

---

# 27. OBSERVABILITY

At minimum log:

- simulation start/stop
- weather fetch status
- Layer 1 calculation status
- model prediction timestamp
- prediction result
- irrigation decision
- simulated actuation
- feedback observation
- error metric update
- training run

Logs must be concise and useful.

Do not spam logs with full datasets.

---

# 28. WHEN THE AGENT FINDS A BUG

Use this order:

1. reproduce;
2. identify root cause;
3. add/adjust a regression test;
4. fix minimally;
5. rerun the relevant test suite;
6. summarize.

Do not mask bugs with:
- broad exception swallowing
- arbitrary defaults
- silent fallbacks
- disabled validation

---

# 29. WHEN THE AGENT WANTS TO MAKE A DESIGN CHANGE

The agent must first identify:

```text
Current approved behavior:
...

Problem:
...

Proposed change:
...

Documents affected:
...

Why the change is necessary:
...
```

Then stop for user approval.

Do not autonomously rewrite architecture.

---

# 30. FIRST-BUILD PRIORITY

The first implementation sequence is:

```text
1. Repository bootstrap
2. AGENTS.md enforcement
3. Environment/config
4. Backend skeleton
5. Database
6. Open-Meteo adapter
7. Layer 1 pure functions
8. Layer 1 tests
9. Simulation engine
10. Physics-forward forecast
11. Synthetic dataset generator
12. Feature engineering
13. XGBoost training/evaluation
14. Prediction service
15. Decision engine
16. Simulated actuation
17. Feedback logging
18. WebSocket live state
19. Frontend shell
20. Dashboard
21. Scenario controls
22. Graphs
23. End-to-end integration
24. Demo hardening
```

Do not jump to UI polish before the computational pipeline works.

---

# 31. DEFINITION OF DONE

A task is DONE only when:

- implementation exists;
- acceptance criteria pass;
- relevant tests pass;
- no known critical error remains;
- data contracts remain compatible;
- no unauthorized dependency was introduced;
- no unrelated architecture was changed.

A visual page that only looks correct but is not connected to the real backend is **not done**.

A model that runs once but has no reproducible training pipeline is **not done**.

A simulation that displays values without running the actual domain logic is **not done**.

---

# 32. FINAL END-TO-END TEST

Before declaring V1 complete, run:

```text
Scenario selected
      ↓
Simulation starts
      ↓
Weather fetched
      ↓
Inputs validated
      ↓
Layer 1 calculates ET₀
      ↓
Kc / ETc calculated
      ↓
Root-zone state calculated
      ↓
Physics +24h forecast generated
      ↓
XGBoost residual applied
      ↓
Final +24h moisture generated
      ↓
Decision engine calculates irrigation state
      ↓
Water requirement calculated
      ↓
Simulated valve operates
      ↓
Simulated field response occurs
      ↓
Flow / pressure / moisture updated
      ↓
Prediction vs actual logged
      ↓
Dashboard updates
```

Every arrow must correspond to real executable code.

---

# 33. FINAL AGENT PRINCIPLE

> **Do not build what sounds impressive. Build what proves the system works.**

The V1 prototype is successful when a judge can change realistic field conditions and immediately observe:

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

The agent's job is to make that loop **correct, reproducible, explainable and demonstrable**.

Nothing more is required for V1.
