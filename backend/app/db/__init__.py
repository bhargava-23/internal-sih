"""
Database layer — SQLAlchemy engine, session management, and models.

This sub-package will contain:

  session.py     — engine creation, session factory, get_session dependency
  models.py      — SQLAlchemy ORM models (all tables from Backend Schema §2–§4)
  repositories/  — typed repository classes for each domain entity

Full schema implementation task: T8-01
Source of truth: docs/04_BACKEND_SCHEMA.docx

RULE: Database models must not contain domain business logic.
Repositories are the only allowed access point for domain services.
"""
