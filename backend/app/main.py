"""
AquaSence AI — FastAPI application entry point.

This module creates the FastAPI app instance and registers:
  - the /health endpoint (required by Backend Schema §8.1)
  - future routers (domain endpoints registered in later tasks)

Domain logic, database models and WebSocket handlers are NOT
implemented here. They belong in their respective modules.

Source of truth: docs/04_BACKEND_SCHEMA.docx §7–§8
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):  # noqa: ARG001
    """
    Application lifespan handler.

    Startup: log configuration summary.
    Shutdown: log graceful stop.

    Database initialization, model loading, and simulation startup
    are implemented in later tasks (T0-03, T8-01).
    """
    logger.info(
        "AquaSence AI starting — env=%s debug=%s",
        settings.app_env,
        settings.debug,
    )
    logger.info("Database URL: %s", settings.database_url)
    logger.info("Simulation seed: %d", settings.simulation_seed)
    yield
    logger.info("AquaSence AI shutting down.")


app = FastAPI(
    title="AquaSence AI",
    description=(
        "Simulation-driven smart irrigation prototype — SIH 2026 / Team Rocket. "
        "V1 is a simulation-only build; all sensor and actuator values are simulated."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — localhost only for V1 prototype
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://{settings.frontend_host}:{settings.frontend_port}",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health endpoint — Backend Schema §8.1
# Minimal stub: later tasks wire in real DB / model / forecast status.
# ---------------------------------------------------------------------------

@app.get(
    "/api/v1/health",
    summary="System health check",
    response_model=dict[str, Any],
    tags=["system"],
)
async def health() -> dict[str, Any]:
    """
    Return the current operational status of the backend.

    Backend Schema §8.1 specifies the full response shape including
    database status, model availability, and forecast freshness.
    Those fields are wired in T8-01 and T8-04.
    """
    return {
        "status": "ok",
        "app_name": settings.app_name,
        "app_env": settings.app_env,
        "version": "0.1.0",
        "prototype_mode": "simulation_v1",
        # Placeholder fields — filled in by later tasks
        "database": "not_initialized",
        "model": {"available": False, "version": None},
        "forecast": {"available": False, "issued_at": None},
    }
