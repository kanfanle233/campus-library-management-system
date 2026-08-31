"""Synchronous SQLAlchemy engine, session entry points, and schema setup."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.database.base import Base


engine = create_engine(
    settings.database_url,
    connect_args={
        "check_same_thread": False,
        "timeout": settings.sqlite_busy_timeout_ms / 1000,
    },
    echo=settings.sqlalchemy_echo,
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _configure_sqlite_connection(dbapi_connection: object, _connection_record: object) -> None:
    """Apply connection-level SQLite safety and concurrency settings."""

    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={settings.sqlite_busy_timeout_ms}")
    finally:
        cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """Yield a request-scoped session; callers/services own transaction commit."""

    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a session context without committing implicitly.

    A failed block is rolled back and every block closes its session. A
    successful block is left uncommitted so a service can decide when and how
    to commit its transaction.
    """

    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Descriptive aliases used by callers that prefer an explicit name.
get_session = get_db
session_context = session_scope


def begin_immediate(session: Session) -> None:
    """Begin SQLite's reserved write transaction on an idle session.

    Services that perform writes can call this before changing rows. It does
    not commit; transaction ownership remains with the service.
    """

    session.connection().exec_driver_sql("BEGIN IMMEDIATE")


def init_db() -> None:
    """Create the SQLite data directory and all ORM tables if absent."""

    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    # Importing models registers every table with Base.metadata before create_all.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
