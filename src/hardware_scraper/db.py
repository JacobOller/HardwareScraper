from __future__ import annotations

from sqlalchemy import Engine, create_engine, event, text


def make_engine(url: str) -> Engine:
    """Create a SQLAlchemy engine with WAL mode enabled for SQLite."""
    engine = create_engine(url)

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _set_wal_mode(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA journal_mode=WAL")
            dbapi_conn.execute("PRAGMA busy_timeout=5000")

    return engine
