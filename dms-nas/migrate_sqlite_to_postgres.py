#!/usr/bin/env python
"""
Sprint 10 — One-time migration: SQLite → PostgreSQL.

Usage:
  python migrate_sqlite_to_postgres.py [--verify] [--dry-run]

Steps:
  1. Read all tables from SQLite
  2. Insert into Postgres (ON CONFLICT DO NOTHING = idempotent)
  3. Reset sequences to max(id)+1
  4. Print verification counts

Run from dms-nas/ root with venv_bot activated.
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("migrate")

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)

from apps.bot.bot_config import (
    DB_PATH, POSTGRES_HOST, POSTGRES_PORT,
    POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD,
)

TABLES_ORDERED = [
    "users",
    "objects",
    "checklists",
    "expiry_items",
    "documents",
    "uploads_log",
    "reminder_log",
    "reports",
    "report_items",
    "packages_log",
    "finance_docs",
    "finance_status_log",
    "problems",
    "doc_links",
    "audit_log",
    "user_objects",
    "ocr_results",
]

BIGSERIAL_TABLES = [
    "users", "objects", "checklists", "expiry_items", "documents",
    "uploads_log", "reminder_log", "reports", "report_items",
    "packages_log", "finance_docs", "finance_status_log",
    "problems", "doc_links", "audit_log", "user_objects", "ocr_results",
]


def sqlite_connect() -> sqlite3.Connection:
    if not os.path.exists(DB_PATH):
        log.error("SQLite DB not found: %s", DB_PATH)
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def pg_connect():
    import psycopg2
    conn = psycopg2.connect(
        host=POSTGRES_HOST, port=POSTGRES_PORT,
        dbname=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASSWORD,
    )
    conn.autocommit = False
    return conn


def migrate_table(sqlite_conn, pg_conn, table: str, dry_run: bool) -> dict:
    """Migrate one table. Returns {table, sqlite_count, pg_inserted, pg_skipped}."""
    rows = sqlite_conn.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        log.info("  %s: empty, skipping", table)
        return {"table": table, "count": 0, "inserted": 0}

    cols = list(rows[0].keys())
    placeholders = ", ".join([f"%s"] * len(cols))
    col_str = ", ".join(f'"{c}"' for c in cols)
    sql = (
        f'INSERT INTO {table} ({col_str}) VALUES ({placeholders}) '
        f'ON CONFLICT DO NOTHING'
    )

    inserted = 0
    cur = pg_conn.cursor()
    for row in rows:
        vals = []
        for c, v in zip(cols, tuple(row)):
            # Convert SQLite INTEGER booleans / None
            vals.append(v)
        if not dry_run:
            cur.execute(sql, vals)
            inserted += cur.rowcount

    if not dry_run:
        pg_conn.commit()

    log.info("  %s: %d rows → inserted %d", table, len(rows), inserted if not dry_run else len(rows))
    return {"table": table, "count": len(rows), "inserted": inserted}


def reset_sequences(pg_conn) -> None:
    """Reset Postgres BIGSERIAL sequences after bulk insert."""
    cur = pg_conn.cursor()
    for table in BIGSERIAL_TABLES:
        try:
            cur.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE(MAX(id), 1)) FROM {table}"
            )
            pg_conn.commit()
            log.info("  Sequence reset: %s", table)
        except Exception as exc:
            pg_conn.rollback()
            log.warning("  Sequence reset skipped %s: %s", table, exc)


def verify_counts(sqlite_conn, pg_conn) -> bool:
    """Compare row counts in both databases."""
    cur = pg_conn.cursor()
    ok = True
    print("\n=== Verification ===")
    print(f"{'Table':<25} {'SQLite':>8} {'Postgres':>10} {'Match':>7}")
    print("-" * 55)
    for table in TABLES_ORDERED:
        try:
            sq = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except Exception:
            sq = "N/A"
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            pg = cur.fetchone()[0]
        except Exception:
            pg = "N/A"

        match = "✅" if sq == pg else "❌"
        if sq != pg:
            ok = False
        print(f"{table:<25} {str(sq):>8} {str(pg):>10} {match:>7}")
    return ok


def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite → Postgres")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be migrated without writing")
    parser.add_argument("--verify", action="store_true",
                        help="Only verify counts, do not migrate")
    parser.add_argument("--tables", nargs="+", default=None,
                        help="Migrate specific tables only")
    args = parser.parse_args()

    log.info("Connecting to SQLite: %s", DB_PATH)
    sqlite_conn = sqlite_connect()

    log.info("Connecting to Postgres: %s@%s:%s/%s",
             POSTGRES_USER, POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB)
    pg_conn = pg_connect()

    if args.verify:
        ok = verify_counts(sqlite_conn, pg_conn)
        sys.exit(0 if ok else 1)

    tables = args.tables or TABLES_ORDERED
    log.info("Migrating %d tables%s...",
             len(tables), " (DRY RUN)" if args.dry_run else "")

    results = []
    for table in tables:
        try:
            r = migrate_table(sqlite_conn, pg_conn, table, args.dry_run)
            results.append(r)
        except Exception as exc:
            log.error("  %s FAILED: %s", table, exc)
            pg_conn.rollback()

    if not args.dry_run:
        log.info("Resetting Postgres sequences...")
        reset_sequences(pg_conn)

    total_rows = sum(r["count"] for r in results)
    log.info("Migration complete: %d tables, %d total rows", len(results), total_rows)

    if not args.dry_run:
        verify_counts(sqlite_conn, pg_conn)

    log.info("""
Next steps:
  1. Set env var: DMS_DB_MODE=postgres
  2. Restart bot:  .\\start_bot.ps1
  3. Restart web:  .\\apps\\web_admin\\start_production.ps1
  4. Verify: GET http://localhost:8000/health
""")


if __name__ == "__main__":
    main()
