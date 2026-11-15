"""Database engine/session setup.

SQLite is the default for local development and the acceptance demo.  The same
models and migrations run on PostgreSQL by pointing ``VLM_DATABASE_URL`` at a
PostgreSQL DSN (see docs/INSTALLATION_MANUAL.md).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings


def _create_engine(url: str) -> Engine:
    kwargs: dict[str, object] = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _record):  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


_settings = get_settings()
engine: Engine = _create_engine(_settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for scripts/worker/tests."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def configure_database(url: str) -> None:
    """Re-bind the module-level engine/session factory (used by tests)."""
    global engine, SessionLocal
    engine = _create_engine(url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
