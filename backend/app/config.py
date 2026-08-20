"""
Application configuration loaded from environment variables.

Uses pydantic-settings to read from .env or the shell environment.
No feature-specific logic lives here — this is pure configuration loading.

Source of truth: .env.example defines all recognized variables.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Runtime configuration for AquaSence AI backend.

    All fields mirror the variables defined in .env.example.
    Defaults match the example values so the app starts without a .env file
    during CI or first checkout.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # ignore unknown env vars gracefully
    )

    # General
    app_name: str = "AquaSence AI"
    app_env: str = "development"
    debug: bool = True
    log_level: str = "INFO"

    # Server addresses
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    frontend_host: str = "127.0.0.1"
    frontend_port: int = 5173

    # Database — SQLite path relative to the working directory
    database_url: str = "sqlite:///./data/aquasence.db"

    # Open-Meteo (the only approved external weather service — TRD Section V1)
    open_meteo_base_url: str = "https://api.open-meteo.com/v1"
    open_meteo_archive_base_url: str = "https://archive-api.open-meteo.com/v1"
    open_meteo_timeout_seconds: int = 15

    # Default field location (Bangalore coordinates in .env.example)
    default_latitude: float = 12.9716
    default_longitude: float = 77.5946
    default_timezone: str = "auto"

    # Simulation defaults
    simulation_seed: int = 42
    simulation_default_scenario: str = "drying"
    simulation_default_duration_hours: int = 168
    simulation_timestep_minutes: int = 60

    # Agronomic defaults
    default_crop: str = "tomato"
    default_growth_stage: str = "flowering"
    default_soil_texture: str = "loam"
    default_root_zone_depth_m: float = 0.60
    default_field_area_m2: float = 100.0
    default_irrigation_efficiency: float = 0.90

    # ML / model paths
    model_path: str = "data/models/xgboost_residual_model.json"
    model_metadata_path: str = "data/models/xgboost_residual_model_metadata.json"
    ml_target_horizon_hours: int = 24
    ml_random_seed: int = 42

    # Data directories
    data_dir: str = "data"
    raw_data_dir: str = "data/raw"
    processed_data_dir: str = "data/processed"
    simulation_data_dir: str = "data/simulation"
    model_dir: str = "data/models"
    metrics_dir: str = "data/metrics"

    # WebSocket
    websocket_heartbeat_seconds: int = 15
    websocket_reconnect_seconds: int = 3

    # Safety flags
    allow_demo_simulation: bool = True
    allow_manual_override: bool = True
    max_simulated_valve_runtime_minutes: int = 120


# Module-level singleton — import this wherever settings are needed.
# Why a singleton here instead of dependency injection everywhere:
# configuration is read-only and does not need mocking in most tests.
settings = Settings()
