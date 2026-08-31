"""SQLAlchemy declarative base and shared column helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def utc_now() -> datetime:
    """Return an aware UTC timestamp suitable for ORM defaults."""

    return datetime.now(timezone.utc)

