"""
Sprint 8/10 — Daily DB backup to NAS.
SQLite mode: uploads dms.db binary.
Postgres mode: runs pg_dump, uploads .sql.gz file.
Keeps 30 daily copies; prunes older ones.
"""

import gzip
import logging
import os
import subprocess
import tempfile
from datetime import datetime, timedelta

logger = logging.getLogger("backup")

NAS_BACKUP_FOLDER = "/Backup/db"
KEEP_DAYS = 30


def run_backup(db_path: str, nas) -> dict:
    """
    Upload DB backup to NAS.
    SQLite: reads .db file directly.
    Postgres: runs pg_dump and gzips the output.
    Returns {"ok": True, ...} or {"ok": False, "error": "..."}
    """
    from core.config import DB_BACKEND as DB_MODE

    today = datetime.now().strftime("%Y%m%d")

    if DB_MODE == "postgres":
        return _backup_postgres(nas, today, NAS_BACKUP_FOLDER, weekly=False)
    else:
        return _backup_sqlite(db_path, nas, today, NAS_BACKUP_FOLDER)


def _backup_sqlite(db_path: str, nas, today: str, folder: str) -> dict:
    if not os.path.exists(db_path):
        err = f"DB file not found: {db_path}"
        logger.error(err)
        return {"ok": False, "error": err}

    try:
        with open(db_path, "rb") as f:
            db_bytes = f.read()
    except Exception as exc:
        logger.error("Backup read failed: %s", exc)
        return {"ok": False, "error": str(exc)}

    filename = f"dms_{today}.db"
    ok = nas.upload(folder, filename, db_bytes, overwrite=True)
    if not ok:
        return {"ok": False, "error": f"NAS upload failed for {filename}"}

    logger.info("SQLite backup uploaded: %s/%s (%d bytes)", folder, filename, len(db_bytes))
    _prune_old_backups(nas, folder, prefix="dms_", suffix=".db")
    return {"ok": True, "filename": filename, "bytes": len(db_bytes)}


def _backup_postgres(nas, today: str, folder: str, weekly: bool = False) -> dict:
    from core.config import (
        PG_HOST as POSTGRES_HOST, PG_PORT as POSTGRES_PORT, PG_DB as POSTGRES_DB,
        PG_USER as POSTGRES_USER, PG_PASS as POSTGRES_PASSWORD,
    )
    prefix = "dms_weekly_" if weekly else "dms_"
    period = datetime.now().strftime("%Y_W%W") if weekly else today
    filename = f"{prefix}{period}.sql.gz"

    env = os.environ.copy()
    env["PGPASSWORD"] = POSTGRES_PASSWORD

    try:
        proc = subprocess.run(
            ["pg_dump",
             "-h", POSTGRES_HOST, "-p", str(POSTGRES_PORT),
             "-U", POSTGRES_USER, "-d", POSTGRES_DB,
             "--no-password", "-Fp"],
            capture_output=True, timeout=120, env=env,
        )
        if proc.returncode != 0:
            err = proc.stderr.decode(errors="replace")[:500]
            logger.error("pg_dump failed: %s", err)
            return {"ok": False, "error": f"pg_dump: {err}"}

        dump_bytes = gzip.compress(proc.stdout)
    except FileNotFoundError:
        logger.error("pg_dump not found in PATH")
        return {"ok": False, "error": "pg_dump not in PATH"}
    except Exception as exc:
        logger.error("pg_dump exception: %s", exc)
        return {"ok": False, "error": str(exc)}

    ok = nas.upload(folder, filename, dump_bytes, overwrite=True)
    if not ok:
        return {"ok": False, "error": f"NAS upload failed for {filename}"}

    logger.info("Postgres backup uploaded: %s/%s (%d bytes)", folder, filename, len(dump_bytes))
    _prune_old_backups(nas, folder, prefix=prefix, suffix=".sql.gz")
    return {"ok": True, "filename": filename, "bytes": len(dump_bytes)}


def _prune_old_backups(nas, folder: str = NAS_BACKUP_FOLDER,
                       prefix: str = "dms_", suffix: str = ".db") -> None:
    """Delete backup files older than KEEP_DAYS days."""
    try:
        files = nas.list_folder(folder)
        cutoff = datetime.now() - timedelta(days=KEEP_DAYS)
        deleted = 0
        for f in files:
            name: str = f.get("name", "")
            if not name.startswith(prefix) or not name.endswith(suffix):
                continue
            try:
                # Extract date part: dms_YYYYMMDD.db or dms_YYYYMMDD.sql.gz
                date_str = name[len(prefix):len(prefix) + 8]
                file_date = datetime.strptime(date_str, "%Y%m%d")
                if file_date < cutoff:
                    nas.delete(f"{folder}/{name}")
                    deleted += 1
            except (ValueError, Exception):
                continue
        if deleted:
            logger.info("Pruned %d old backup(s) from %s", deleted, folder)
    except Exception as exc:
        logger.warning("Backup prune error: %s", exc)


def run_weekly_backup(db_path: str, nas) -> dict:
    """Weekly backup to separate folder."""
    from core.config import DB_BACKEND as DB_MODE

    folder = "/Backup/weekly"
    week = datetime.now().strftime("%Y_W%W")

    if DB_MODE == "postgres":
        return _backup_postgres(nas, week, folder, weekly=True)

    if not os.path.exists(db_path):
        return {"ok": False, "error": "DB not found"}

    with open(db_path, "rb") as f:
        db_bytes = f.read()

    filename = f"dms_weekly_{week}.db"
    ok = nas.upload(folder, filename, db_bytes, overwrite=True)
    if ok:
        logger.info("Weekly backup: %s/%s", folder, filename)
        return {"ok": True, "filename": filename}
    return {"ok": False, "error": "NAS upload failed"}
