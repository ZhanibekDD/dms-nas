"""
tools/verify_pg.py
──────────────────
Сравнивает COUNT(*) каждой таблицы между SQLite и PostgreSQL.
Запускать ПОСЛЕ migrate_sqlite_to_pg.py.

Запуск (из корня dms-nas/):
    python tools/verify_pg.py

Вывод:
    ✓  table_name        SQLite=1234  PG=1234
    ✗  table_name        SQLite=1234  PG=0     ← расхождение!
"""

import sys
import sqlite3
import logging
from pathlib import Path

import psycopg2
import psycopg2.extras

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import (
    SQLITE_PATH,
    PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
log = logging.getLogger("verify")

TABLES = [
    "users",
    "objects",
    "uploads_log",
    "finance_docs",
    "expiry_items",
    "reports",
    "packages_log",
    "documents",
    "user_object_access",
    "finance_status_log",
    "reminder_log",
    "report_items",
    "doc_links",
    "problems",
    "ocr_results",
    "audit_log",
]


def sqlite_count(conn: sqlite3.Connection, table: str) -> int:
    try:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return row[0] if row else 0
    except Exception:
        return -1


def pg_count(pg_conn, table: str) -> int:
    try:
        with pg_conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            row = cur.fetchone()
            return row["count"] if row else 0
    except Exception:
        pg_conn.rollback()
        return -1


def main() -> None:
    print("=" * 64)
    print("DMS-NAS  ·  Verify SQLite → PostgreSQL migration")
    print(f"SQLite : {SQLITE_PATH}")
    print(f"PG     : {PG_USER}@{PG_HOST}:{PG_PORT}/{PG_DB}")
    print("=" * 64)

    if not Path(SQLITE_PATH).exists():
        print(f"ERROR: SQLite not found: {SQLITE_PATH}")
        sys.exit(1)

    sq_conn = sqlite3.connect(SQLITE_PATH)

    try:
        pg_conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, dbname=PG_DB,
            user=PG_USER, password=PG_PASS,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
    except Exception as exc:
        print(f"ERROR: cannot connect to PG: {exc}")
        sq_conn.close()
        sys.exit(1)

    # Определяем какие таблицы реально есть в SQLite
    sq_tables_raw = sq_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    sq_tables = {row[0] for row in sq_tables_raw}

    ok_count = 0
    fail_count = 0
    skip_count = 0

    print(f"\n{'Таблица':<28}  {'SQLite':>8}  {'PG':>8}  {'Статус'}")
    print("─" * 64)

    for table in TABLES:
        if table not in sq_tables:
            sq_cnt = 0
            pg_cnt = pg_count(pg_conn, table)
            mark = "·"
            status = "нет в SQLite"
            skip_count += 1
        else:
            sq_cnt = sqlite_count(sq_conn, table)
            pg_cnt = pg_count(pg_conn, table)

            if sq_cnt < 0:
                mark = "?"
                status = "ошибка SQLite"
                skip_count += 1
            elif pg_cnt < 0:
                mark = "!"
                status = "таблица не найдена в PG"
                fail_count += 1
            elif sq_cnt == pg_cnt:
                mark = "✓"
                status = "OK"
                ok_count += 1
            else:
                mark = "✗"
                diff = sq_cnt - pg_cnt
                status = f"РАСХОЖДЕНИЕ! missing={diff:+d}"
                fail_count += 1

        print(f"  {mark}  {table:<26}  {sq_cnt:>8}  {pg_cnt:>8}  {status}")

    print("─" * 64)
    print(f"\n  Совпало: {ok_count}   Ошибок: {fail_count}   Пропущено: {skip_count}")
    print()

    sq_conn.close()
    pg_conn.close()

    if fail_count > 0:
        print("ПРОВЕРКА НЕ ПРОШЛА — есть расхождения между SQLite и PG.")
        print("Запустите migrate ещё раз или исправьте схему PG.")
        sys.exit(1)
    else:
        print("Все таблицы совпадают. Можно переключать DB_BACKEND=\"postgres\".")


if __name__ == "__main__":
    main()
