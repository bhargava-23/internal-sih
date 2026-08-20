"""
Database engine and session management.

Creates the SQLAlchemy engine from the DATABASE_URL in settings.
Provides a session factory and a FastAPI dependency for request-scoped sessions.

The full ORM model definitions are added in task T8-01 (db/models.py).
This module only handles connection infrastructure.

Source of truth: docs/04_BACKEND_SCHEMA.docx §1 (database technology)
TRD: SQLite + SQLAlchemy 2.0
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


def _ensure_data_dir(database_url: str) -> None:
    """
    Ensure the directory for a SQLite database file exists.

    SQLite will fail with an error if the parent directory is missing.
    This is a no-op for non-SQLite URLs.
    """
    if database_url.startswith("sqlite:///"):
        # sqlite:///./data/aquasence.db  →  ./data/aquasence.db
        db_path = database_url.replace("sqlite:///", "")
        parent = Path(db_path).parent
        parent.mkdir(parents=True, exist_ok=True)


# Create the directory before connecting so SQLite can write the file
_ensure_data_dir(settings.database_url)

engine = create_engine(
    settings.database_url,
    # connect_args is SQLite-specific; prevents issues with multiple threads
    connect_args={"check_same_thread": False},
    echo=settings.debug,  # log SQL only in debug mode
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    class_=Session,
)


# ---------------------------------------------------------------------------
# Declarative base — all ORM models inherit from this.
# Models are defined in app/db/models.py (task T8-01).
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """
    SQLAlchemy declarative base for all AquaSence ORM models.

    Centralised here so models.py can simply do:
        from app.db.session import Base
        class Zone(Base): ...
    """


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


def get_session():
    """
    Yield a request-scoped SQLAlchemy session.

    Usage in route handlers:
        from fastapi import Depends
        from app.db.session import get_session

        @router.get(...)
        def my_route(db: Session = Depends(get_session)):
            ...
    """
    with SessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# Database health check helper
# ---------------------------------------------------------------------------


def check_database_reachable() -> bool:
    """
    Return True if the database can be queried; False otherwise.

    Used by the /health endpoint (later wired in T8-01).
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
