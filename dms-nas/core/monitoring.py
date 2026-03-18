"""
Sprint 8 — Monitoring & Alerts.
Sends Telegram messages to all admin users when critical events occur.
Works without async context — uses plain requests directly to Bot API.
"""

import logging
import threading
import time
from datetime import datetime
from typing import Callable

import requests

logger = logging.getLogger("monitoring")

# Filled by bot.py on startup
_BOT_TOKEN: str = ""
_GET_ADMIN_IDS: Callable[[], list[int]] = lambda: []

# NAS failure counters per caller (reset on success)
_nas_fail_counts: dict[str, int] = {}
NAS_ALERT_THRESHOLD = 2   # alert after this many consecutive failures


def configure(bot_token: str, get_admin_ids_fn: Callable[[], list[int]]) -> None:
    global _BOT_TOKEN, _GET_ADMIN_IDS
    _BOT_TOKEN = bot_token
    _GET_ADMIN_IDS = get_admin_ids_fn


def _send(telegram_id: int, text: str) -> bool:
    if not _BOT_TOKEN:
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{_BOT_TOKEN}/sendMessage",
            json={"chat_id": telegram_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception as exc:
        logger.error("monitoring._send failed: %s", exc)
        return False


def alert_admins(message: str) -> None:
    """Send alert to all admin users. Non-blocking (runs in thread)."""
    def _run():
        ids = _GET_ADMIN_IDS()
        if not ids:
            logger.warning("ALERT (no admins): %s", message)
            return
        text = f"🚨 <b>DMS ALERT</b>\n{datetime.now():%Y-%m-%d %H:%M}\n\n{message}"
        for tid in ids:
            _send(tid, text)
        logger.warning("ALERT sent to %d admins: %s", len(ids), message)

    threading.Thread(target=_run, daemon=True).start()


def nas_op_ok(caller: str = "default") -> None:
    """Call after successful NAS op to reset failure counter."""
    _nas_fail_counts[caller] = 0


def nas_op_failed(caller: str, detail: str = "") -> None:
    """
    Call after failed NAS op.
    Sends alert when consecutive failures reach NAS_ALERT_THRESHOLD.
    """
    count = _nas_fail_counts.get(caller, 0) + 1
    _nas_fail_counts[caller] = count
    logger.error("NAS failure #%d caller=%s %s", count, caller, detail)
    if count >= NAS_ALERT_THRESHOLD:
        alert_admins(
            f"⚠️ NAS недоступен\nКалбэк: <code>{caller}</code>\n"
            f"Попыток подряд: {count}\n{detail}"
        )


def alert_scheduler_error(job_name: str, exc: Exception) -> None:
    alert_admins(
        f"⏰ Ошибка планировщика\nЗадача: <code>{job_name}</code>\n"
        f"Ошибка: <code>{exc}</code>"
    )


def alert_package_failed(object_name: str, error: str) -> None:
    alert_admins(
        f"📦 Ошибка формирования пакета\n"
        f"Объект: <code>{object_name}</code>\n"
        f"Ошибка: <code>{error}</code>"
    )


def alert_backup_failed(error: str) -> None:
    alert_admins(
        f"💾 Ошибка резервного копирования БД\n"
        f"Ошибка: <code>{error}</code>"
    )
