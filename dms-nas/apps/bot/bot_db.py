"""
Database layer — Sprint 10 refactor.
Uses SQLAlchemy text() queries: works with SQLite (default) and PostgreSQL.
All public function signatures remain identical to the previous version.

DB_MODE is set in apps/bot/bot_config.py (env var DMS_DB_MODE).
"""

import json
import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy import text

from core.database import read_conn, write_conn, insert_row, row_to_dict, rows_to_list, init_schema
from apps.bot.bot_config import DB_PATH

logger = logging.getLogger("bot_db")


# ──────────────────────────────────────────────────────────────────────────────
# Schema — SQLite dialect (used by init_db for SQLite)
# For Postgres see core/schema_postgres.sql
# ──────────────────────────────────────────────────────────────────────────────

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id  INTEGER UNIQUE NOT NULL,
    username     TEXT,
    full_name    TEXT,
    role         TEXT    DEFAULT 'viewer',
    is_active    INTEGER DEFAULT 1,
    created_at   TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS objects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    nas_path    TEXT,
    description TEXT,
    is_active   INTEGER DEFAULT 1,
    created_by  INTEGER,
    created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_objects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    object_name TEXT    NOT NULL,
    granted_by  INTEGER,
    granted_at  TEXT    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(telegram_id, object_name)
);

CREATE TABLE IF NOT EXISTS documents (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    object_name       TEXT    NOT NULL,
    category          TEXT    NOT NULL DEFAULT 'build',
    doc_type          TEXT,
    status            TEXT    DEFAULT 'pending',
    nas_path          TEXT    NOT NULL,
    file_hash         TEXT,
    file_size         INTEGER,
    original_filename TEXT,
    created_by        INTEGER,
    created_at        TEXT    DEFAULT CURRENT_TIMESTAMP,
    updated_at        TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS uploads_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id   INTEGER NOT NULL,
    filename      TEXT,
    nas_path      TEXT,
    doc_type      TEXT,
    object_name   TEXT,
    section       TEXT,
    review_status TEXT    DEFAULT 'pending',
    reject_reason TEXT,
    reviewed_by   INTEGER,
    reviewed_at   TEXT,
    uploaded_at   TEXT    DEFAULT CURRENT_TIMESTAMP,
    tags          TEXT    DEFAULT '[]',
    doc_id        INTEGER
);

CREATE TABLE IF NOT EXISTS expiry_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id  INTEGER NOT NULL,
    title        TEXT    NOT NULL,
    object_name  TEXT,
    doc_path     TEXT,
    expires_at   TEXT    NOT NULL,
    status       TEXT    DEFAULT 'active',
    created_at   TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reminder_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    expiry_id   INTEGER NOT NULL,
    days_before INTEGER NOT NULL,
    sent_at     TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS checklists (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    items      TEXT    NOT NULL,
    created_at TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id   INTEGER NOT NULL,
    object_name   TEXT    NOT NULL,
    checklist_id  INTEGER,
    report_date   TEXT,
    nas_folder    TEXT,
    status        TEXT    DEFAULT 'in_progress',
    created_at    TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS report_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id   INTEGER NOT NULL,
    item_index  INTEGER NOT NULL,
    item_name   TEXT    NOT NULL,
    nas_path    TEXT,
    uploaded_at TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS packages_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id  INTEGER NOT NULL,
    object_name  TEXT,
    period       TEXT,
    doc_types    TEXT,
    nas_zip_path TEXT,
    file_count   INTEGER DEFAULT 0,
    status       TEXT    DEFAULT 'created',
    created_at   TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS finance_docs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id   INTEGER NOT NULL,
    object_name   TEXT,
    doc_type      TEXT,
    filename      TEXT,
    nas_path      TEXT,
    amount        REAL,
    counterparty  TEXT,
    status        TEXT    DEFAULT 'черновик',
    created_at    TEXT    DEFAULT CURRENT_TIMESTAMP,
    updated_at    TEXT    DEFAULT CURRENT_TIMESTAMP,
    doc_id        INTEGER
);

CREATE TABLE IF NOT EXISTS finance_status_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    finance_doc_id INTEGER NOT NULL,
    old_status     TEXT,
    new_status     TEXT,
    changed_by     INTEGER,
    comment        TEXT,
    changed_at     TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS problems (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_id   INTEGER,
    label       TEXT,
    description TEXT,
    status      TEXT    DEFAULT 'open',
    created_by  INTEGER NOT NULL,
    created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS doc_links (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    from_type  TEXT    NOT NULL,
    from_id    INTEGER NOT NULL,
    to_type    TEXT    NOT NULL,
    to_id      INTEGER NOT NULL,
    created_by INTEGER,
    created_at TEXT    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(from_type, from_id, to_type, to_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER,
    action      TEXT,
    entity_type TEXT,
    entity_id   INTEGER,
    detail      TEXT,
    created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ocr_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_id     INTEGER,
    doc_id        INTEGER,
    status        TEXT    DEFAULT 'pending',
    doc_number    TEXT,
    doc_date      TEXT,
    expires_at    TEXT,
    counterparty  TEXT,
    amount        REAL,
    confidence    INTEGER DEFAULT 0,
    raw_text      TEXT,
    reviewed_by   INTEGER,
    reviewed_at   TEXT,
    created_at    TEXT    DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (upload_id) REFERENCES uploads_log(id) ON DELETE SET NULL,
    FOREIGN KEY (doc_id)    REFERENCES documents(id)   ON DELETE SET NULL
);
"""


def init_db() -> None:
    init_schema(SCHEMA_SQLITE)
    logger.info("DB initialised at %s", DB_PATH)


# ──────────────────────────────────────────────────────────────────────────────
# Users
# ──────────────────────────────────────────────────────────────────────────────

def get_user(telegram_id: int) -> Optional[dict]:
    with read_conn() as conn:
        row = conn.execute(
            text("SELECT * FROM users WHERE telegram_id = :tid"),
            {"tid": telegram_id}
        ).fetchone()
        return row_to_dict(row)


def upsert_user(telegram_id: int, username: str, full_name: str,
                role: str = "viewer") -> None:
    with write_conn() as conn:
        conn.execute(text("""
            INSERT INTO users (telegram_id, username, full_name, role)
            VALUES (:tid, :uname, :fname, :role)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username  = excluded.username,
                full_name = excluded.full_name
        """), {"tid": telegram_id, "uname": username, "fname": full_name, "role": role})


def set_user_role(telegram_id: int, role: str) -> None:
    with write_conn() as conn:
        conn.execute(
            text("UPDATE users SET role = :role WHERE telegram_id = :tid"),
            {"role": role, "tid": telegram_id}
        )


def set_user_active(telegram_id: int, active: bool) -> None:
    with write_conn() as conn:
        conn.execute(
            text("UPDATE users SET is_active = :a WHERE telegram_id = :tid"),
            {"a": 1 if active else 0, "tid": telegram_id}
        )


def list_users() -> list[dict]:
    with read_conn() as conn:
        return rows_to_list(
            conn.execute(text("SELECT * FROM users ORDER BY created_at DESC")).fetchall()
        )


# ──────────────────────────────────────────────────────────────────────────────
# User ↔ Object permissions
# ──────────────────────────────────────────────────────────────────────────────

def get_allowed_objects(telegram_id: int) -> list[str]:
    """Return list of allowed object names. Empty = all allowed."""
    with read_conn() as conn:
        rows = conn.execute(
            text("SELECT object_name FROM user_objects WHERE telegram_id = :tid"),
            {"tid": telegram_id}
        ).fetchall()
        return [r._mapping["object_name"] for r in rows]


def grant_object_access(telegram_id: int, object_name: str, granted_by: int = 0) -> None:
    with write_conn() as conn:
        conn.execute(text("""
            INSERT OR IGNORE INTO user_objects (telegram_id, object_name, granted_by)
            VALUES (:tid, :obj, :gb)
        """), {"tid": telegram_id, "obj": object_name, "gb": granted_by})


def revoke_object_access(telegram_id: int, object_name: str) -> None:
    with write_conn() as conn:
        conn.execute(text("""
            DELETE FROM user_objects WHERE telegram_id = :tid AND object_name = :obj
        """), {"tid": telegram_id, "obj": object_name})


def get_all_objects() -> list:
    """Return distinct object_name values from uploads_log for picker menus."""
    with read_conn() as conn:
        rows = conn.execute(
            text("SELECT DISTINCT object_name FROM uploads_log ORDER BY object_name")
        ).fetchall()
        return [r._mapping["object_name"] for r in rows if r._mapping["object_name"]]


def list_all_object_accesses() -> list:
    """Return all (telegram_id, object_name) pairs sorted by telegram_id."""
    with read_conn() as conn:
        rows = conn.execute(
            text("SELECT telegram_id, object_name FROM user_objects ORDER BY telegram_id, object_name")
        ).fetchall()
        return [(r._mapping["telegram_id"], r._mapping["object_name"]) for r in rows]


# ──────────────────────────────────────────────────────────────────────────────
# Documents registry (Sprint 11)
# ──────────────────────────────────────────────────────────────────────────────

def create_document(object_name: str, category: str, doc_type: str,
                    nas_path: str, original_filename: str,
                    file_hash: str = "", file_size: int = 0,
                    created_by: int = 0) -> int:
    """Create a document registry entry. Returns new doc_id."""
    with write_conn() as conn:
        return insert_row(conn, """
            INSERT INTO documents
                (object_name, category, doc_type, nas_path,
                 original_filename, file_hash, file_size, created_by)
            VALUES
                (:obj, :cat, :dtype, :path, :fname, :fhash, :fsize, :cb)
        """, {
            "obj": object_name, "cat": category, "dtype": doc_type,
            "path": nas_path, "fname": original_filename,
            "fhash": file_hash, "fsize": file_size, "cb": created_by,
        })


def get_document(doc_id: int) -> Optional[dict]:
    with read_conn() as conn:
        return row_to_dict(conn.execute(
            text("SELECT * FROM documents WHERE id = :id"), {"id": doc_id}
        ).fetchone())


def find_document_by_hash(file_hash: str) -> Optional[dict]:
    """Check if file already exists (deduplication)."""
    if not file_hash:
        return None
    with read_conn() as conn:
        return row_to_dict(conn.execute(
            text("SELECT * FROM documents WHERE file_hash = :h LIMIT 1"),
            {"h": file_hash}
        ).fetchone())


def update_document_status(doc_id: int, status: str) -> None:
    now = datetime.utcnow().isoformat()
    with write_conn() as conn:
        conn.execute(
            text("UPDATE documents SET status = :s, updated_at = :now WHERE id = :id"),
            {"s": status, "now": now, "id": doc_id}
        )


def list_documents(object_name: str = None, category: str = None,
                   status: str = None, limit: int = 50) -> list[dict]:
    conds, params = [], {}
    if object_name:
        conds.append("object_name = :obj"); params["obj"] = object_name
    if category:
        conds.append("category = :cat"); params["cat"] = category
    if status:
        conds.append("status = :st"); params["st"] = status
    where = f"WHERE {' AND '.join(conds)}" if conds else ""
    params["lim"] = limit
    with read_conn() as conn:
        return rows_to_list(conn.execute(
            text(f"SELECT * FROM documents {where} ORDER BY created_at DESC LIMIT :lim"),
            params
        ).fetchall())


# ──────────────────────────────────────────────────────────────────────────────
# Uploads
# ──────────────────────────────────────────────────────────────────────────────

def log_upload(telegram_id: int, filename: str, nas_path: str,
               doc_type: str, object_name: str, section: str = "",
               doc_id: int = None) -> int:
    with write_conn() as conn:
        new_id = insert_row(conn, """
            INSERT INTO uploads_log
                (telegram_id, filename, nas_path, doc_type, object_name, section, doc_id)
            VALUES (:tid, :fname, :path, :dtype, :obj, :sec, :docid)
        """, {
            "tid": telegram_id, "fname": filename, "path": nas_path,
            "dtype": doc_type, "obj": object_name, "sec": section, "docid": doc_id,
        })
        logger.info("Upload logged id=%d user=%d path=%s", new_id, telegram_id, nas_path)
        return new_id


def get_upload(upload_id: int) -> Optional[dict]:
    with read_conn() as conn:
        return row_to_dict(conn.execute(
            text("SELECT * FROM uploads_log WHERE id = :id"), {"id": upload_id}
        ).fetchone())


def list_uploads_today(telegram_id: int) -> list[dict]:
    today = date.today().isoformat()
    with read_conn() as conn:
        return rows_to_list(conn.execute(text("""
            SELECT * FROM uploads_log
            WHERE telegram_id = :tid AND date(uploaded_at) = :today
            ORDER BY uploaded_at DESC
        """), {"tid": telegram_id, "today": today}).fetchall())


def list_pending_uploads(limit: int = 20) -> list[dict]:
    with read_conn() as conn:
        return rows_to_list(conn.execute(text("""
            SELECT u.*, us.full_name, us.role
            FROM uploads_log u
            LEFT JOIN users us ON us.telegram_id = u.telegram_id
            WHERE u.review_status = 'pending'
            ORDER BY u.uploaded_at DESC LIMIT :lim
        """), {"lim": limit}).fetchall())


def set_review_status(upload_id: int, status: str, reviewer_id: int,
                      reason: str = "") -> None:
    now = datetime.utcnow().isoformat()
    with write_conn() as conn:
        conn.execute(text("""
            UPDATE uploads_log
            SET review_status = :st, reviewed_by = :rb,
                reviewed_at = :now, reject_reason = :reason
            WHERE id = :id
        """), {"st": status, "rb": reviewer_id, "now": now, "reason": reason, "id": upload_id})


def search_uploads(query: str, object_name: str = None,
                   doc_type: str = None, limit: int = 20) -> list[dict]:
    conds = ["(filename LIKE :q OR object_name LIKE :q)"]
    params: dict = {"q": f"%{query}%"}
    if object_name:
        conds.append("object_name = :obj"); params["obj"] = object_name
    if doc_type:
        conds.append("doc_type = :dtype"); params["dtype"] = doc_type
    params["lim"] = limit
    with read_conn() as conn:
        return rows_to_list(conn.execute(text(
            f"SELECT * FROM uploads_log WHERE {' AND '.join(conds)} "
            f"ORDER BY uploaded_at DESC LIMIT :lim"
        ), params).fetchall())


# ──────────────────────────────────────────────────────────────────────────────
# Expiry
# ──────────────────────────────────────────────────────────────────────────────

def add_expiry(telegram_id: int, title: str, object_name: str,
               expires_at: str, doc_path: str = "") -> int:
    with write_conn() as conn:
        return insert_row(conn, """
            INSERT INTO expiry_items (telegram_id, title, object_name, expires_at, doc_path)
            VALUES (:tid, :title, :obj, :exp, :path)
        """, {"tid": telegram_id, "title": title, "obj": object_name,
              "exp": expires_at, "path": doc_path})


def get_active_expiry_items() -> list[dict]:
    with read_conn() as conn:
        return rows_to_list(conn.execute(text(
            "SELECT * FROM expiry_items WHERE status = 'active' ORDER BY expires_at"
        )).fetchall())


def list_expiry_for_user(telegram_id: int) -> list[dict]:
    with read_conn() as conn:
        return rows_to_list(conn.execute(text("""
            SELECT * FROM expiry_items
            WHERE telegram_id = :tid AND status = 'active'
            ORDER BY expires_at
        """), {"tid": telegram_id}).fetchall())


def archive_expiry(expiry_id: int) -> None:
    with write_conn() as conn:
        conn.execute(
            text("UPDATE expiry_items SET status = 'archived' WHERE id = :id"),
            {"id": expiry_id}
        )


def reminder_sent_today(expiry_id: int, days_before: int) -> bool:
    today = date.today().isoformat()
    with read_conn() as conn:
        row = conn.execute(text("""
            SELECT 1 FROM reminder_log
            WHERE expiry_id = :eid AND days_before = :db AND date(sent_at) = :today
        """), {"eid": expiry_id, "db": days_before, "today": today}).fetchone()
        return row is not None


def log_reminder(expiry_id: int, days_before: int) -> None:
    with write_conn() as conn:
        conn.execute(
            text("INSERT INTO reminder_log (expiry_id, days_before) VALUES (:eid, :db)"),
            {"eid": expiry_id, "db": days_before}
        )


# ──────────────────────────────────────────────────────────────────────────────
# Photo reports
# ──────────────────────────────────────────────────────────────────────────────

def create_report(telegram_id: int, object_name: str, checklist_id: Optional[int],
                  report_date: str, nas_folder: str) -> int:
    with write_conn() as conn:
        return insert_row(conn, """
            INSERT INTO reports (telegram_id, object_name, checklist_id, report_date, nas_folder)
            VALUES (:tid, :obj, :clid, :rdate, :folder)
        """, {"tid": telegram_id, "obj": object_name, "clid": checklist_id,
              "rdate": report_date, "folder": nas_folder})


def get_report(report_id: int) -> Optional[dict]:
    with read_conn() as conn:
        return row_to_dict(conn.execute(
            text("SELECT * FROM reports WHERE id = :id"), {"id": report_id}
        ).fetchone())


def add_report_item(report_id: int, item_index: int,
                    item_name: str, nas_path: str) -> None:
    with write_conn() as conn:
        conn.execute(text("""
            INSERT INTO report_items (report_id, item_index, item_name, nas_path)
            VALUES (:rid, :idx, :name, :path)
            ON CONFLICT DO NOTHING
        """), {"rid": report_id, "idx": item_index, "name": item_name, "path": nas_path})


def finish_report(report_id: int) -> None:
    with write_conn() as conn:
        conn.execute(
            text("UPDATE reports SET status = 'done' WHERE id = :id"), {"id": report_id}
        )


def get_checklist(checklist_id: int) -> Optional[dict]:
    with read_conn() as conn:
        return row_to_dict(conn.execute(
            text("SELECT * FROM checklists WHERE id = :id"), {"id": checklist_id}
        ).fetchone())


def list_checklists() -> list[dict]:
    with read_conn() as conn:
        return rows_to_list(
            conn.execute(text("SELECT * FROM checklists ORDER BY id")).fetchall()
        )


def add_checklist(name: str, items: list[str]) -> int:
    with write_conn() as conn:
        return insert_row(conn,
            "INSERT INTO checklists (name, items) VALUES (:name, :items)",
            {"name": name, "items": json.dumps(items, ensure_ascii=False)}
        )


# ──────────────────────────────────────────────────────────────────────────────
# Packages
# ──────────────────────────────────────────────────────────────────────────────

def log_package(telegram_id: int, object_name: str, period: str,
                doc_types: list[str], nas_zip_path: str, file_count: int) -> int:
    with write_conn() as conn:
        return insert_row(conn, """
            INSERT INTO packages_log
                (telegram_id, object_name, period, doc_types, nas_zip_path, file_count)
            VALUES (:tid, :obj, :period, :dtypes, :zip, :cnt)
        """, {
            "tid": telegram_id, "obj": object_name, "period": period,
            "dtypes": json.dumps(doc_types, ensure_ascii=False),
            "zip": nas_zip_path, "cnt": file_count,
        })


# ──────────────────────────────────────────────────────────────────────────────
# Finance
# ──────────────────────────────────────────────────────────────────────────────

def add_finance_doc(telegram_id: int, object_name: str, doc_type: str,
                    filename: str, nas_path: str,
                    amount: Optional[float] = None,
                    counterparty: str = "",
                    doc_id: int = None) -> int:
    with write_conn() as conn:
        return insert_row(conn, """
            INSERT INTO finance_docs
                (telegram_id, object_name, doc_type, filename,
                 nas_path, amount, counterparty, doc_id)
            VALUES (:tid, :obj, :dtype, :fname, :path, :amt, :cp, :docid)
        """, {
            "tid": telegram_id, "obj": object_name, "dtype": doc_type,
            "fname": filename, "path": nas_path, "amt": amount,
            "cp": counterparty, "docid": doc_id,
        })


def get_finance_doc(doc_id: int) -> Optional[dict]:
    with read_conn() as conn:
        return row_to_dict(conn.execute(
            text("SELECT * FROM finance_docs WHERE id = :id"), {"id": doc_id}
        ).fetchone())


def list_finance_docs(object_name: str = None, status: str = None,
                      telegram_id: int = None, limit: int = 50) -> list[dict]:
    conds, params = [], {}
    if object_name:
        conds.append("object_name = :obj"); params["obj"] = object_name
    if status:
        conds.append("status = :st"); params["st"] = status
    if telegram_id:
        conds.append("telegram_id = :tid"); params["tid"] = telegram_id
    where = f"WHERE {' AND '.join(conds)}" if conds else ""
    params["lim"] = limit
    with read_conn() as conn:
        return rows_to_list(conn.execute(text(
            f"SELECT * FROM finance_docs {where} ORDER BY created_at DESC LIMIT :lim"
        ), params).fetchall())


def update_finance_status(doc_id: int, new_status: str,
                          user_id: int, comment: str = "") -> None:
    now = datetime.utcnow().isoformat()
    with write_conn() as conn:
        row = conn.execute(
            text("SELECT status FROM finance_docs WHERE id = :id"), {"id": doc_id}
        ).fetchone()
        old = row._mapping["status"] if row else ""
        conn.execute(
            text("UPDATE finance_docs SET status = :s, updated_at = :now WHERE id = :id"),
            {"s": new_status, "now": now, "id": doc_id}
        )
        conn.execute(text("""
            INSERT INTO finance_status_log
                (finance_doc_id, old_status, new_status, changed_by, comment)
            VALUES (:fid, :old, :new, :cb, :cmt)
        """), {"fid": doc_id, "old": old, "new": new_status, "cb": user_id, "cmt": comment})


# ──────────────────────────────────────────────────────────────────────────────
# Problems
# ──────────────────────────────────────────────────────────────────────────────

def add_problem(created_by: int, label: str, description: str,
                upload_id: Optional[int] = None) -> int:
    with write_conn() as conn:
        return insert_row(conn,
            "INSERT INTO problems (upload_id, label, description, created_by) "
            "VALUES (:uid, :label, :desc, :cb)",
            {"uid": upload_id, "label": label, "desc": description, "cb": created_by}
        )


def list_problems(status: str = "open", limit: int = 30) -> list[dict]:
    with read_conn() as conn:
        return rows_to_list(conn.execute(text("""
            SELECT p.*, u.full_name
            FROM problems p
            LEFT JOIN users u ON u.telegram_id = p.created_by
            WHERE p.status = :st ORDER BY p.created_at DESC LIMIT :lim
        """), {"st": status, "lim": limit}).fetchall())


def close_problem(problem_id: int) -> None:
    with write_conn() as conn:
        conn.execute(
            text("UPDATE problems SET status = 'closed' WHERE id = :id"), {"id": problem_id}
        )


# ──────────────────────────────────────────────────────────────────────────────
# doc_links
# ──────────────────────────────────────────────────────────────────────────────

def add_link(from_type: str, from_id: int, to_type: str, to_id: int,
             created_by: int = 0) -> Optional[int]:
    try:
        with write_conn() as conn:
            return insert_row(conn, """
                INSERT OR IGNORE INTO doc_links
                    (from_type, from_id, to_type, to_id, created_by)
                VALUES (:ft, :fid, :tt, :tid, :cb)
            """, {"ft": from_type, "fid": from_id, "tt": to_type, "tid": to_id, "cb": created_by})
    except Exception as exc:
        logger.error("add_link failed: %s", exc)
        return None


def remove_link(from_type: str, from_id: int, to_type: str, to_id: int) -> bool:
    with write_conn() as conn:
        conn.execute(text("""
            DELETE FROM doc_links
            WHERE from_type = :ft AND from_id = :fid AND to_type = :tt AND to_id = :tid
        """), {"ft": from_type, "fid": from_id, "tt": to_type, "tid": to_id})
        return True


def get_links(entity_type: str, entity_id: int) -> list[dict]:
    with read_conn() as conn:
        return rows_to_list(conn.execute(text("""
            SELECT * FROM doc_links
            WHERE (from_type = :et AND from_id = :eid)
               OR (to_type   = :et AND to_id   = :eid)
            ORDER BY created_at DESC
        """), {"et": entity_type, "eid": entity_id}).fetchall())


# ──────────────────────────────────────────────────────────────────────────────
# Objects registry
# ──────────────────────────────────────────────────────────────────────────────

def register_object(name: str, nas_path: str = "", description: str = "",
                    created_by: int = 0) -> int:
    with write_conn() as conn:
        try:
            return insert_row(conn,
                "INSERT INTO objects (name, nas_path, description, created_by) "
                "VALUES (:name, :path, :desc, :cb)",
                {"name": name, "path": nas_path or f"/{name}",
                 "desc": description, "cb": created_by}
            )
        except Exception:
            row = conn.execute(
                text("SELECT id FROM objects WHERE name = :n"), {"n": name}
            ).fetchone()
            return row._mapping["id"] if row else 0


def list_objects(active_only: bool = True) -> list[dict]:
    with read_conn() as conn:
        sql = "SELECT * FROM objects"
        if active_only:
            sql += " WHERE is_active = 1"
        return rows_to_list(conn.execute(text(sql + " ORDER BY name")).fetchall())


# ──────────────────────────────────────────────────────────────────────────────
# Audit
# ──────────────────────────────────────────────────────────────────────────────

def audit(telegram_id: int, action: str, entity_type: str,
          entity_id: int, detail: str = "") -> None:
    with write_conn() as conn:
        conn.execute(text("""
            INSERT INTO audit_log (telegram_id, action, entity_type, entity_id, detail)
            VALUES (:tid, :action, :etype, :eid, :detail)
        """), {
            "tid": telegram_id, "action": action,
            "entity_type": entity_type, "eid": entity_id, "detail": detail,
        })
    logger.debug("AUDIT user=%d %s %s#%d", telegram_id, action, entity_type, entity_id)


# ──────────────────────────────────────────────────────────────────────────────
# Sprint 13 helpers
# ──────────────────────────────────────────────────────────────────────────────

def get_uploads_since(since_date: str, status: Optional[str] = None) -> list[dict]:
    """Return uploads created on or after since_date (ISO). Optionally filter by status."""
    sql = "SELECT * FROM uploads_log WHERE uploaded_at >= :since"
    params: dict = {"since": since_date}
    if status:
        sql += " AND review_status = :st"
        params["st"] = status
    with read_conn() as conn:
        return rows_to_list(conn.execute(text(sql), params).fetchall())


def get_users_by_role(role: str) -> list[dict]:
    """Return all users with the given role."""
    with read_conn() as conn:
        return rows_to_list(conn.execute(
            text("SELECT * FROM users WHERE role = :role"),
            {"role": role}
        ).fetchall())


# ──────────────────────────────────────────────────────────────────────────────
# Sprint 12: OCR results
# ──────────────────────────────────────────────────────────────────────────────

def create_ocr_result(upload_id: Optional[int], doc_id: Optional[int],
                      ocr_data: dict) -> int:
    """Save OCR extraction result. Returns new id."""
    with write_conn() as conn:
        return insert_row(conn, """
            INSERT INTO ocr_results
                (upload_id, doc_id, doc_number, doc_date, expires_at,
                 counterparty, amount, confidence, raw_text, status)
            VALUES
                (:uid, :did, :dn, :dd, :ea, :cp, :amt, :conf, :rt, 'pending')
        """, {
            "uid":  upload_id,
            "did":  doc_id,
            "dn":   ocr_data.get("doc_number"),
            "dd":   ocr_data.get("doc_date"),
            "ea":   ocr_data.get("expires_at"),
            "cp":   ocr_data.get("counterparty"),
            "amt":  ocr_data.get("amount"),
            "conf": ocr_data.get("confidence", 0),
            "rt":   ocr_data.get("raw_text", "")[:2000],
        })


def get_ocr_result(ocr_id: int) -> Optional[dict]:
    with read_conn() as conn:
        row = conn.execute(
            text("SELECT * FROM ocr_results WHERE id = :id"), {"id": ocr_id}
        ).fetchone()
        return row_to_dict(row)


def confirm_ocr_result(ocr_id: int, confirmed_data: dict, reviewed_by: int) -> None:
    """Mark OCR result as confirmed and update fields."""
    from core.utils import now_iso
    with write_conn() as conn:
        conn.execute(text("""
            UPDATE ocr_results SET
                doc_number   = :dn,
                doc_date     = :dd,
                expires_at   = :ea,
                counterparty = :cp,
                amount       = :amt,
                status       = 'confirmed',
                reviewed_by  = :rb,
                reviewed_at  = :ra
            WHERE id = :id
        """), {
            "dn":  confirmed_data.get("doc_number"),
            "dd":  confirmed_data.get("doc_date"),
            "ea":  confirmed_data.get("expires_at"),
            "cp":  confirmed_data.get("counterparty"),
            "amt": confirmed_data.get("amount"),
            "rb":  reviewed_by,
            "ra":  now_iso(),
            "id":  ocr_id,
        })


def reject_ocr_result(ocr_id: int, reviewed_by: int) -> None:
    from core.utils import now_iso
    with write_conn() as conn:
        conn.execute(text("""
            UPDATE ocr_results SET status='rejected', reviewed_by=:rb, reviewed_at=:ra
            WHERE id = :id
        """), {"rb": reviewed_by, "ra": now_iso(), "id": ocr_id})


def list_pending_ocr() -> list[dict]:
    with read_conn() as conn:
        return rows_to_list(conn.execute(
            text("SELECT * FROM ocr_results WHERE status='pending' ORDER BY created_at DESC")
        ).fetchall())


def get_ocr_for_doc(doc_id: int) -> Optional[dict]:
    with read_conn() as conn:
        row = conn.execute(
            text("SELECT * FROM ocr_results WHERE doc_id=:did ORDER BY id DESC LIMIT 1"),
            {"did": doc_id}
        ).fetchone()
        return row_to_dict(row)
