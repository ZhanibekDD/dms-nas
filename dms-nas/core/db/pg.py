"""
core/db/pg.py — PostgreSQL connection pool & transaction helpers.

Используется напрямую ядром; bot_db.py и Django работают через core.database.
Все параметры берутся из core.config — без .env.
"""

import logging
from contextlib import contextmanager
from typing import Optional, Any, Generator

import psycopg2
import psycopg2.extras
import psycopg2.pool

logger = logging.getLogger("core.db.pg")

# ── Пул соединений ────────────────────────────────────────────────────────────
_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None


def _cfg():
    """Ленивый импорт конфига, чтобы избежать циклических зависимостей."""
    from core.config import PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASS, PG_POOL_SIZE, PG_MAX_OVERFLOW
    return dict(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB,
        user=PG_USER, password=PG_PASS,
        min_conn=1, max_conn=PG_POOL_SIZE + PG_MAX_OVERFLOW,
    )


def get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Вернуть глобальный пул (создать при первом вызове)."""
    global _pool
    if _pool is None or _pool.closed:
        c = _cfg()
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=c["min_conn"],
            maxconn=c["max_conn"],
            host=c["host"], port=c["port"], dbname=c["dbname"],
            user=c["user"], password=c["password"],
            cursor_factory=psycopg2.extras.RealDictCursor,
            options="-c client_encoding=UTF8",
        )
        logger.info("PG pool created: %s@%s:%s/%s (max=%s)",
                    c["user"], c["host"], c["port"], c["dbname"], c["max_conn"])
    return _pool


def close_pool() -> None:
    """Закрыть пул (вызывать при остановке приложения)."""
    global _pool
    if _pool and not _pool.closed:
        _pool.closeall()
    _pool = None


@contextmanager
def get_conn() -> Generator:
    """
    Контекстный менеджер: взять соединение из пула, вернуть после блока.
    Транзакция НЕ открывается автоматически.

    Пример:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    """
    pool = get_pool()
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)


@contextmanager
def transaction() -> Generator:
    """
    Контекстный менеджер: соединение + транзакция (commit/rollback).

    Пример:
        with transaction() as cur:
            cur.execute("INSERT INTO ...")
            return cur.fetchone()["id"]
    """
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def fetchone(sql: str, params: tuple | dict = ()) -> Optional[dict]:
    """Выполнить SELECT и вернуть первую строку как dict (или None)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()


def fetchall(sql: str, params: tuple | dict = ()) -> list[dict]:
    """Выполнить SELECT и вернуть все строки как list[dict]."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() or []


def execute(sql: str, params: tuple | dict = ()) -> None:
    """Выполнить DML-команду в транзакции (commit автоматически)."""
    with transaction() as cur:
        cur.execute(sql, params)


def insert_returning(sql: str, params: tuple | dict = ()) -> Any:
    """
    INSERT … RETURNING id  → вернуть значение первого столбца.
    SQL должен содержать RETURNING.
    """
    with transaction() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        if row is None:
            return None
        return next(iter(row.values()))


def table_count(table: str) -> int:
    """SELECT COUNT(*) FROM <table>."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS cnt FROM {table}")
            row = cur.fetchone()
            return row["cnt"] if row else 0


def ping() -> bool:
    """Проверить связь с БД (True = ОК)."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception as exc:
        logger.error("PG ping failed: %s", exc)
        return False
