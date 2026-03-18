"""
tools/migrate_sqlite_to_pg.py
─────────────────────────────
Разовая миграция данных SQLite → PostgreSQL.

Что делает:
  1. Читает таблицы из SQLite в правильном порядке (с учётом FK)
  2. Вставляет строки в PG батчами по BATCH_SIZE
  3. Сбрасывает sequences (BIGSERIAL) чтобы следующий INSERT взял правильный ID
  4. Если таблица в PG уже не пустая — пропускает (для повторного запуска)

Запуск (из корня dms-nas/):
    python tools/migrate_sqlite_to_pg.py

Требования:
    pip install psycopg2-binary sqlalchemy
"""

import sys
import logging
import sqlite3
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

# ── Добавляем корень проекта в sys.path ───────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import (
    SQLITE_PATH,
    PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASS,
)

# ── Логирование ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("migrate")

# ── Параметры ─────────────────────────────────────────────────────────────────
BATCH_SIZE = 500     # строк за один INSERT

# Порядок таблиц — строго по зависимостям FK
TABLES_ORDERED = [
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
    "audit_log",            # последним — самая большая
]

# Таблицы с BIGSERIAL — сбросим sequence после вставки
BIGSERIAL_TABLES = {
    "uploads_log":       "uploads_log_id_seq",
    "finance_docs":      "finance_docs_id_seq",
    "expiry_items":      "expiry_items_id_seq",
    "reports":           "reports_id_seq",
    "packages_log":      "packages_log_id_seq",
    "documents":         "documents_doc_id_seq",
    "finance_status_log":"finance_status_log_id_seq",
    "reminder_log":      "reminder_log_id_seq",
    "report_items":      "report_items_id_seq",
    "doc_links":         "doc_links_id_seq",
    "problems":          "problems_id_seq",
    "ocr_results":       "ocr_results_id_seq",
    "audit_log":         "audit_log_id_seq",
}


# ── Конвертация типов ─────────────────────────────────────────────────────────
def _coerce(value: Any) -> Any:
    """Привести значение SQLite к типу, совместимому с psycopg2."""
    if isinstance(value, (datetime, date)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    # bytes → memoryview для BYTEA в PG (или оставить как есть)
    return value


def _coerce_row(row: dict) -> dict:
    return {k: _coerce(v) for k, v in row.items()}


# ── Получить список таблиц, которые реально есть в SQLite ────────────────────
def _sqlite_tables(sqlite_conn: sqlite3.Connection) -> set[str]:
    cur = sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    return {row[0] for row in cur.fetchall()}


# ── Получить COUNT(*) из PG ───────────────────────────────────────────────────
def _pg_count(pg_conn, table: str) -> int:
    with pg_conn.cursor() as cur:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            return cur.fetchone()["count"]
        except Exception:
            pg_conn.rollback()
            return -1


# ── Сбросить sequence ─────────────────────────────────────────────────────────
def _reset_sequence(pg_conn, table: str, seq_name: str) -> None:
    with pg_conn.cursor() as cur:
        cur.execute(f"SELECT MAX(id) FROM {table}")
        row = cur.fetchone()
        max_id = row["max"] if row and row["max"] is not None else 0
        if max_id > 0:
            cur.execute(
                f"SELECT setval('{seq_name}', %s, true)", (max_id,)
            )
    pg_conn.commit()
    log.debug("  sequence %s → %s", seq_name, max_id)


# ── Мигрировать одну таблицу ──────────────────────────────────────────────────
def migrate_table(table: str,
                  sqlite_conn: sqlite3.Connection,
                  pg_conn) -> tuple[int, int]:
    """
    Вернуть (sqlite_rows, inserted_rows).
    Если PG-таблица уже содержит данные — вернуть (N, 0) (пропуск).
    """
    # Читаем из SQLite
    sqlite_conn.row_factory = sqlite3.Row
    cur_sq = sqlite_conn.execute(f"SELECT * FROM {table}")
    rows = [dict(r) for r in cur_sq.fetchall()]
    total_sq = len(rows)

    if total_sq == 0:
        log.info("  %-25s  0 rows in SQLite — skip", table)
        return 0, 0

    # Проверяем PG
    pg_cnt = _pg_count(pg_conn, table)
    if pg_cnt < 0:
        log.warning("  %-25s  table not found in PG — skip", table)
        return total_sq, 0
    if pg_cnt > 0:
        log.info("  %-25s  PG already has %d rows — skip (idempotent)", table, pg_cnt)
        return total_sq, 0

    # Получаем список колонок из первой строки
    columns = list(rows[0].keys())
    placeholders = ", ".join([f"%({col})s" for col in columns])
    cols_str = ", ".join(columns)
    sql = f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders})"

    inserted = 0
    with pg_conn.cursor() as cur:
        try:
            pg_conn.autocommit = False
            for batch_start in range(0, total_sq, BATCH_SIZE):
                batch = [_coerce_row(r) for r in rows[batch_start:batch_start + BATCH_SIZE]]
                psycopg2.extras.execute_batch(cur, sql, batch, page_size=BATCH_SIZE)
                inserted += len(batch)
                log.debug("    %s: %d/%d", table, inserted, total_sq)
            pg_conn.commit()
        except Exception as exc:
            pg_conn.rollback()
            log.error("  %-25s  ERROR: %s", table, exc)
            return total_sq, 0

    # Сбросить sequence
    if table in BIGSERIAL_TABLES:
        _reset_sequence(pg_conn, table, BIGSERIAL_TABLES[table])

    return total_sq, inserted


# ── Главная функция ───────────────────────────────────────────────────────────
def main() -> None:
    log.info("═" * 60)
    log.info("DMS-NAS  ·  SQLite → PostgreSQL migration")
    log.info("SQLite : %s", SQLITE_PATH)
    log.info("PG     : %s@%s:%s/%s", PG_USER, PG_HOST, PG_PORT, PG_DB)
    log.info("═" * 60)

    # Открываем SQLite
    if not Path(SQLITE_PATH).exists():
        log.error("SQLite file not found: %s", SQLITE_PATH)
        sys.exit(1)

    sqlite_conn = sqlite3.connect(SQLITE_PATH, check_same_thread=False)
    sqlite_conn.execute("PRAGMA journal_mode=WAL")
    sqlite_tables = _sqlite_tables(sqlite_conn)
    log.info("SQLite tables found: %s", sorted(sqlite_tables))

    # Открываем PG
    try:
        pg_conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, dbname=PG_DB,
            user=PG_USER, password=PG_PASS,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        pg_conn.autocommit = False
        log.info("PG connection OK")
    except Exception as exc:
        log.error("Cannot connect to PG: %s", exc)
        sqlite_conn.close()
        sys.exit(1)

    # Мигрируем
    results: list[tuple[str, int, int]] = []
    for table in TABLES_ORDERED:
        if table not in sqlite_tables:
            log.info("  %-25s  not in SQLite — skip", table)
            results.append((table, 0, 0))
            continue

        sq_cnt, pg_inserted = migrate_table(table, sqlite_conn, pg_conn)
        results.append((table, sq_cnt, pg_inserted))

    sqlite_conn.close()
    pg_conn.close()

    # Итоговый отчёт
    log.info("")
    log.info("═" * 60)
    log.info("РЕЗУЛЬТАТ МИГРАЦИИ")
    log.info("%-25s  %8s  %8s  %s", "Таблица", "SQLite", "В PG", "Статус")
    log.info("─" * 60)
    total_sq = total_pg = 0
    for table, sq, pg in results:
        status = "✓ OK" if pg == sq else ("⏭ SKIP" if pg == 0 and sq > 0 else "· пусто")
        log.info("%-25s  %8d  %8d  %s", table, sq, pg, status)
        total_sq += sq
        total_pg += pg
    log.info("─" * 60)
    log.info("%-25s  %8d  %8d", "ИТОГО", total_sq, total_pg)
    log.info("═" * 60)

    if total_pg == 0 and total_sq > 0:
        log.error("Ни одна строка не была перенесена! Проверьте схему PG.")
        sys.exit(1)
    elif total_pg < total_sq:
        skipped = total_sq - total_pg
        log.warning("Пропущено %d строк (уже были в PG или таблица отсутствует)", skipped)
    else:
        log.info("Миграция завершена успешно.")

    log.info("")
    log.info("Следующий шаг — проверка:")
    log.info("  python tools/verify_pg.py")
    log.info("")
    log.info("Затем включить Postgres:")
    log.info("  В core/config.py  →  DB_BACKEND = \"postgres\"")


if __name__ == "__main__":
    main()
