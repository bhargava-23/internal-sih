# AquaSence AI

**Team:** Team Rocket | **Programme:** Smart India Hackathon 2026 | **Problem ID:** SIH260220

---

## Purpose

AquaSence AI automatically regulates irrigation valves based on soil-moisture availability in the crop root zone, using artificial intelligence, in piped and micro-irrigation networks.

The system combines a deterministic FAO-56 agronomic engine (Layer 1) with an XGBoost residual forecasting model (Layer 2) to produce 24-hour moisture forecasts and irrigation decisions. A rule-based decision engine — not the ML model — holds authority over valve actuation.

## V1 Prototype — Simulation-Driven

> **This is a simulation-driven V1 prototype.**
>
> Physical field sensors, pumps, valves, flow meters, and pressure sensors are represented by realistic simulated inputs and simulated field responses. The downstream computational pipeline (agronomic engine → physics forecast → XGBoost residual → decision → actuation → feedback logging) is real.
>
> Simulated observations are clearly labelled `source: simulation_v1`. No simulated metric is presented as real-field accuracy.

---

## Local Setup

### Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.11+ (3.13 recommended) |
| Node.js | 18+ (22 recommended) |
| npm | 9+ |
| uv | 0.12+ (Python package manager) |

### 1 — Clone and configure

```bash
git clone <repo-url>
cd AquaSence-AI
cp .env.example .env
# Edit .env if needed (all defaults work for local development)
```

### 2 — Backend

```bash
cd backend
py -3.13 -m uv sync --dev    # install dependencies + generate uv.lock
py -3.13 -m uv run pytest    # run test suite
py -3.13 -m uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API is available at `http://127.0.0.1:8000`.  
OpenAPI docs: `http://127.0.0.1:8000/docs`

### 3 — Frontend

```bash
cd frontend
npm install
npm run dev      # development server on http://localhost:5173
npm run build    # production build
```

---

## Repository Structure

```
AquaSence-AI/
│
├── AGENTS.md                    # AI agent operating contract
├── .env.example                 # Environment variable template
│
├── docs/                        # Specification documents (read-only)
│   ├── 01_MASTER_PRD.docx
│   ├── 02_SIMULATION_PROTOTYPE_SPEC.docx
│   ├── 03_TRD.docx
│   ├── 04_BACKEND_SCHEMA.docx
│   ├── 05_LAYER1_SPEC.docx
│   ├── 06_LAYER2_SPEC.docx
│   ├── 07_FEEDBACK_SPEC.docx
│   ├── 08_APP_FLOW.docx
│   ├── 09_UIUX_BRIEF.docx
│   ├── 10_IMPLEMENTATION_PLAN.docx
│   └── reference/               # Reference material (non-authoritative)
│
├── backend/                     # FastAPI + Python backend
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── config.py            # Environment configuration
│   │   ├── domain/
│   │   │   ├── layer1/          # FAO-56 agronomic engine (T1-xx)
│   │   │   ├── layer2/          # XGBoost residual model (T6-xx)
│   │   │   ├── decision/        # Irrigation decision engine (T7-01)
│   │   │   ├── simulation/      # Deterministic scenario engine (T2-xx)
│   │   │   └── feedback/        # Prediction logging (T7-03)
│   │   ├── adapters/            # Open-Meteo, simulation sensors (T3-xx)
│   │   ├── api/                 # FastAPI routers (T8-xx)
│   │   └── db/                  # SQLAlchemy session + models (T8-01)
│   └── tests/
│
├── frontend/                    # React + TypeScript + Vite dashboard
│
├── simulation/                  # Standalone simulation utilities
├── agronomy/                    # Agronomic reference data
├── ml/                          # ML experiment scripts
├── data/                        # Generated data, models, metrics
├── scripts/                     # CLI utilities
└── tests/
    └── fixtures/                # Shared test fixtures (read-only)
        ├── layer1_golden_test_cases.json
        ├── scenario_fixtures.json
        └── README.md
```

---

## Decision Pipeline

```
Simulated Inputs (soil moisture / weather / rainfall)
        ↓
Layer 1 — FAO-56 Agronomic Engine (ET₀, ETc, TAW, RAW, depletion)
        ↓
Physics-Forward 24h Forecast
        ↓
Layer 2 — XGBoost Residual Model (corrects physics baseline)
        ↓
Decision Engine (irrigation trigger + water volume)
        ↓
Simulated Valve / Actuator
        ↓
Simulated Field Response (moisture, flow, pressure update)
        ↓
Feedback Log → Offline Retraining
```

---

## Specification Documents

| Document | Controls |
|----------|---------|
| `01_MASTER_PRD` | Product scope, objectives, SIH requirements |
| `02_SIMULATION_PROTOTYPE_SPEC` | V1 prototype behaviour, demo scenarios |
| `03_TRD` | Technology stack, runtime architecture |
| `04_BACKEND_SCHEMA` | Database schema, API contracts, WebSocket events |
| `05_LAYER1_SPEC` | FAO-56 equations, agronomic parameters |
| `06_LAYER2_SPEC` | XGBoost residual model, feature contract, leakage rules |
| `07_FEEDBACK_SPEC` | Sensor QC, prediction/outcome logging, offline retraining |
| `08_APP_FLOW` | Screens, navigation, user workflows |
| `09_UIUX_BRIEF` | Visual design, typography, colour palette |
| `10_IMPLEMENTATION_PLAN` | Task sequence, acceptance criteria |
