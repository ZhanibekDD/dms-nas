"""
Expiry / deadline tracking and daily reminder dispatcher.
"""

import logging
from datetime import date, datetime, timedelta

logger = logging.getLogger("svc.expiry")

REMINDER_DAYS = [30, 7, 1]


def check_and_send_reminders(db, send_fn) -> int:
    """
    Called daily at 09:00. Sends T-30/T-7/T-1/Expired notifications.
    send_fn(telegram_id, message_text) — async-safe callable.
    Returns number of reminders sent.
    """
    today = date.today()
    items = db.get_active_expiry_items()
    sent = 0

    for item in items:
        try:
            exp_date = date.fromisoformat(item["expires_at"])
        except (ValueError, TypeError):
            continue

        delta = (exp_date - today).days

        if delta < 0:
            # Expired — notify once per day (check reminder_log)
            if not db.reminder_sent_today(item["id"], 0):
                msg = (
                    f"🔴 ПРОСРОЧЕНО: {item['title']}\n"
                    f"Объект: {item['object_name']}\n"
                    f"Истёк: {item['expires_at']}"
                )
                try:
                    send_fn(item["telegram_id"], msg)
                    db.log_reminder(item["id"], 0)
                    sent += 1
                except Exception as exc:
                    logger.warning("reminder send failed item=%d: %s", item["id"], exc)
            continue

        for days_before in REMINDER_DAYS:
            if delta == days_before:
                if not db.reminder_sent_today(item["id"], days_before):
                    if days_before == 1:
                        prefix = "🟠 ЗАВТРА истекает"
                    elif days_before == 7:
                        prefix = "🟡 Через 7 дней истекает"
                    else:
                        prefix = f"🔵 Через {days_before} дней истекает"

                    msg = (
                        f"{prefix}: {item['title']}\n"
                        f"Объект: {item['object_name']}\n"
                        f"Срок: {item['expires_at']}"
                    )
                    try:
                        send_fn(item["telegram_id"], msg)
                        db.log_reminder(item["id"], days_before)
                        sent += 1
                    except Exception as exc:
                        logger.warning("reminder send failed item=%d: %s", item["id"], exc)

    logger.info("Expiry check complete, sent=%d", sent)
    return sent
