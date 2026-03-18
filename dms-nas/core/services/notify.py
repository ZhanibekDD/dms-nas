"""
Sprint 13: Web → Telegram notifications.

Sends messages to Telegram users from the Django web admin
(e.g., approve/reject events, weekly digest).
Uses httpx synchronous client (already a dependency via python-telegram-bot).
"""

import logging
import threading
import httpx

logger = logging.getLogger("core.notify")


def _bot_token() -> str:
    """Return bot token from bot_config (centralized, no .env)."""
    import sys, os
    root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    if root not in sys.path:
        sys.path.insert(0, root)
    from apps.bot.bot_config import TELEGRAM_TOKEN
    return TELEGRAM_TOKEN


def send_telegram(telegram_id: int, text: str, parse_mode: str = "Markdown") -> bool:
    """
    Send a Telegram message synchronously.
    Returns True on success.
    """
    token = _bot_token()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = httpx.post(
            url,
            json={"chat_id": telegram_id, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
        if resp.status_code == 200:
            return True
        logger.warning("Telegram notify failed: %s %s", resp.status_code, resp.text[:200])
        return False
    except Exception as exc:
        logger.error("Telegram notify error: %s", exc)
        return False


def notify_async(telegram_id: int, text: str) -> None:
    """Fire-and-forget notification in a background thread (safe from Django views)."""
    t = threading.Thread(
        target=send_telegram,
        args=(telegram_id, text),
        daemon=True,
    )
    t.start()


# ─────────────────────────────────────────────────────────────────────────────
# High-level notification helpers
# ─────────────────────────────────────────────────────────────────────────────

def notify_doc_approved(telegram_id: int, filename: str, doc_id: int,
                        reviewer: str = "Администратор") -> None:
    text = (
        f"✅ *Документ утверждён*\n\n"
        f"📄 *{filename}*\n"
        f"👤 Проверил: {reviewer}\n"
        f"🆔 ID: {doc_id}\n\n"
        f"Документ принят и доступен в системе."
    )
    notify_async(telegram_id, text)


def notify_doc_rejected(telegram_id: int, filename: str, doc_id: int,
                        reviewer: str = "Администратор",
                        reason: str = "") -> None:
    text = (
        f"❌ *Документ отклонён*\n\n"
        f"📄 *{filename}*\n"
        f"👤 Проверил: {reviewer}\n"
        f"🆔 ID: {doc_id}\n"
    )
    if reason:
        text += f"📝 Причина: {reason}\n"
    text += "\nПожалуйста, загрузите исправленную версию."
    notify_async(telegram_id, text)


def notify_finance_status(telegram_id: int, counterparty: str,
                          amount: float, new_status: str,
                          reviewer: str = "Администратор") -> None:
    icons = {
        "утверждён": "✅",
        "отклонён":  "❌",
        "оплачен":   "💳",
        "на_проверке": "⏳",
    }
    icon = icons.get(new_status, "ℹ️")
    text = (
        f"{icon} *Финансовый документ: статус изменён*\n\n"
        f"🏢 Контрагент: {counterparty}\n"
        f"💰 Сумма: {amount:,.2f}\n"
        f"📊 Новый статус: *{new_status}*\n"
        f"👤 Изменил: {reviewer}"
    )
    notify_async(telegram_id, text)


def send_weekly_digest(admin_telegram_ids: list, stats: dict) -> None:
    """
    Send weekly digest to a list of admin Telegram IDs.
    stats dict keys: uploads, approved, rejected, fin_total, fin_paid,
                     expiry_active, expiry_overdue, open_problems
    """
    text = (
        f"📊 *Еженедельный дайджест DMS-NAS*\n\n"
        f"📄 Загрузок за неделю: *{stats.get('uploads_week', 0)}*\n"
        f"✅ Утверждено: *{stats.get('approved_week', 0)}*\n"
        f"❌ Отклонено: *{stats.get('rejected_week', 0)}*\n\n"
        f"💰 Финдоков всего: *{stats.get('fin_total', 0)}*\n"
        f"💳 Оплачено: *{stats.get('fin_paid', 0)}*\n\n"
        f"⏰ Активных сроков: *{stats.get('expiry_active', 0)}*\n"
        f"🔴 Просрочено: *{stats.get('expiry_overdue', 0)}*\n"
        f"⚠️ Открытых проблем: *{stats.get('open_problems', 0)}*"
    )
    for tid in admin_telegram_ids:
        notify_async(tid, text)
