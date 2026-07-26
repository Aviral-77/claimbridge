"""Database layer — SQLAlchemy engine + session (Phase A2).

Postgres is the store. `DATABASE_URL` is required — docker-compose sets it, and
the app refuses to start without it (no silent fallback to a non-scalable store).
SQLite is supported ONLY when a test explicitly passes a `sqlite://` URL.

Schema on Postgres is managed by **Alembic** (`alembic upgrade head`); the
SQLite/test path uses `create_all`.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from logging_setup import get_logger
from models import Base

log = get_logger("db")

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. ClaimBridge uses Postgres as its store — run "
        "the stack with `docker compose --env-file .env.docker up`, or point "
        "DATABASE_URL at a Postgres instance. (SQLite is for tests only: pass an "
        "explicit sqlite:// URL.)"
    )

_is_sqlite = DATABASE_URL.startswith("sqlite")


def _masked(url: str) -> str:
    """Hide the password when logging the connection string."""
    if "@" in url and "//" in url:
        head, tail = url.split("//", 1)
        creds, host = tail.split("@", 1)
        user = creds.split(":", 1)[0]
        return f"{head}//{user}:***@{host}"
    return url


_engine_kwargs = dict(pool_pre_ping=True, future=True)
if _is_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs.update(pool_size=10, max_overflow=20)

engine = create_engine(DATABASE_URL, **_engine_kwargs)
log.info("engine created: %s (sqlite=%s)", _masked(DATABASE_URL), _is_sqlite)

SessionLocal = sessionmaker(
    bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    """Ensure the schema exists.

    Postgres: schema is owned by Alembic — run `alembic upgrade head` (the Docker
    api command does this on start). SQLite/tests: create tables directly.
    """
    if _is_sqlite:
        Base.metadata.create_all(engine)
        log.info("sqlite schema created via create_all (test mode)")
    else:
        log.info("postgres schema is managed by Alembic — skipping create_all")


def get_db():
    """FastAPI dependency: yield a session, always close it after the request."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
