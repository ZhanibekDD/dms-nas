"""
apps/bot/bot_config.py
──────────────────────
DEPRECATED — все настройки теперь в core/config.py.

Этот файл оставлен для обратной совместимости.
Он просто реэкспортирует всё из core.config.
"""

# Re-export everything from the single source of truth
from core.config import (   # noqa: F401
    BOT_TOKEN,
    NAS_BASE_URL, NAS_USER, NAS_PASSWORD, NAS_HTTPS,
    NAS_ROOT_SHARES,

    DB_BACKEND as DB_MODE,
    DB_DSN,
    SQLITE_PATH as DB_PATH,
    SQLITE_DSN as DB_DSN_SQLITE,

    PG_HOST as POSTGRES_HOST,
    PG_PORT as POSTGRES_PORT,
    PG_DB   as POSTGRES_DB,
    PG_USER as POSTGRES_USER,
    PG_PASS as POSTGRES_PASSWORD,

    DJANGO_DB,

    ROLE_PERMISSIONS,
    ROLE_LABELS,
    DOC_TYPES,
    FINANCE_TYPES,
    FINANCE_TRANSITIONS,
    OBJECT_TEMPLATE,
    EXPIRY_HOUR,
    REMINDER_DAYS,
    WHITELIST,
    DEFAULT_CHECKLIST,
    ADMIN_IDS,
)
