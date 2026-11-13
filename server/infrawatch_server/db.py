from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url or url in ("sqlite://", "sqlite:///"):
            kwargs["poolclass"] = StaticPool
        engine = create_engine(url, **kwargs)

        @event.listens_for(engine, "connect")
        def _fk(dbapi_conn, _):  # enforce FKs on SQLite
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        return engine
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url, pool_pre_ping=True)


class Database:
    def __init__(self, url: str):
        self.engine = make_engine(url)
        self.sessionmaker = sessionmaker(self.engine, expire_on_commit=False)

    def create_all(self) -> None:
        from . import models  # noqa: F401

        Base.metadata.create_all(self.engine)
        if self.engine.dialect.name == "postgresql":
            _enable_timescale(self.engine)

    def session(self) -> Session:
        return self.sessionmaker()


def _enable_timescale(engine: Engine) -> None:
    """Best effort: convert metrics/service_checks to hypertables if TimescaleDB is present."""
    import logging

    from sqlalchemy import text

    log = logging.getLogger("infrawatch.db")
    try:
        with engine.begin() as c:
            c.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
    except Exception as exc:  # plain PostgreSQL: the schema works without it
        log.info("TimescaleDB not available, using plain PostgreSQL tables (%s)", type(exc).__name__)
        return
    for table in ("metrics", "service_checks"):
        try:
            with engine.begin() as c:
                c.execute(text(f"SELECT create_hypertable('{table}', 'ts', if_not_exists => TRUE, migrate_data => TRUE)"))
        except Exception as exc:
            log.warning("could not create hypertable %s: %s", table, exc)
