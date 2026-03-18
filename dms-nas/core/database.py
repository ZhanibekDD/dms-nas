"""
Sprint 10 — Unified database engine.
Supports SQLite (dev/default) and PostgreSQL (prod) via SQLAlchemy 2.x.

Usage in bot_db.py:
    from core.database import read_conn, write_conn, insert_row

    with read_conn() as conn:
        row = conn.execute(text("SELECT * FROM users WHERE telegram_id = :tid"),
                           {"tid": uid}).fetchone()
        return row_to_dict(row)

    with write_conn() as conn:
        new_id = insert_row(conn,
            "INSERT INTO users (telegram_id, role) VALUES (:tid, :role)",
            {"tid": uid, "role": "viewer"})
"""

import logging
from contextlib import contextmanager
from typing import Optional, Any

from sqlalchemy import create_engine, text, Engine

logger = logging.getLogger("database")

_engine: Optional[Engine] = None


def _get_engine() -> Engine:
    global _engine
    if _engine is not None:
        return _engine

    from apps.bot.bot_config import DB_MODE, DB_DSN

    if DB_MODE == "sqlite":
        _engine = create_engine(
            DB_DSN,
            connect_args={"check_same_thread": False},
            echo=False,
        )
    else:
        _engine = create_engine(
            DB_DSN,
            pool_pre_ping=True,   # detect stale connections
            pool_size=5,
            max_overflow=10,
            echo=False,
        )
    logger.info("DB engine created: %s mode=%s", DB_DSN[:40], DB_MODE)
    return _engine


def reset_engine() -> None:
    """Force re-creation of engine (use after config change)."""
    global _engine
    if _engine:
        _engine.dispose()
    _engine = None


@contextmanager
def read_conn():
    """Context manager for read-only queries (no auto-commit needed)."""
    with _get_engine().connect() as conn:
        yield conn


@contextmanager
def write_conn():
    """Context manager for write queries — auto-commits on success, rolls back on error."""
    with _get_engine().begin() as conn:
        yield conn


def insert_row(conn, sql: str, params: dict) -> int:
    """
    Execute INSERT and return new row ID.
    Handles SQLite (last_insert_rowid) vs Postgres (RETURNING id) automatically.
    """
    from apps.bot.bot_config import DB_MODE

    if DB_MODE == "postgres":
        pg_sql = sql.rstrip().rstrip(";")
        if "RETURNING" not in pg_sql.upper():
            pg_sql += " RETURNING id"
        result = conn.execute(text(pg_sql), params)
        return result.scalar() or 0
    else:
        conn.execute(text(sql), params)
        return conn.execute(text("SELECT last_insert_rowid()")).scalar() or 0


def row_to_dict(row) -> Optional[dict]:
    """Convert SQLAlchemy Row to plain dict (or None)."""
    if row is None:
        return None
    return dict(row._mapping)


def rows_to_list(rows) -> list[dict]:
    """Convert list of SQLAlchemy Rows to list of dicts."""
    return [dict(r._mapping) for r in rows]


def init_schema(schema_sql: str) -> None:
    """
    Execute a multi-statement schema SQL.
    Works for both SQLite (executescript) and Postgres (split on ';').
    """
    from apps.bot.bot_config import DB_MODE

    statements = [s.strip() for s in schema_sql.split(";") if s.strip()]

    if DB_MODE == "sqlite":
        # For SQLite, executescript is most reliable
        raw_conn = _get_engine().raw_connection()
        try:
            raw_conn.executescript(schema_sql)
            raw_conn.commit()
        finally:
            raw_conn.close()
    else:
        with write_conn() as conn:
            for stmt in statements:
                if stmt:
                    try:
                        conn.execute(text(stmt))
                    except Exception as exc:
                        # Log but don't fail on "already exists"
                        if "already exists" not in str(exc).lower():
                            logger.warning("Schema stmt warning: %s | %s", exc, stmt[:60])
