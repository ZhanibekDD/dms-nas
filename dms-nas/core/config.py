"""
core/config.py — Единый источник конфигурации DMS-NAS.

Все модули (bot, web, core) читают настройки ТОЛЬКО отсюда.
Никакого .env — все значения хранятся прямо в коде.

Для переопределения в продакшене создайте:
    core/config_local.py   (добавлен в .gitignore)
и задайте в нём нужные переменные — они перезапишут значения ниже.
"""

import pathlib

# ──────────────────────────────────────────────────────────────────────────────
# Пути
# ──────────────────────────────────────────────────────────────────────────────
_ROOT = pathlib.Path(__file__).resolve().parent.parent   # dms-nas/

# ──────────────────────────────────────────────────────────────────────────────
# Telegram
# ──────────────────────────────────────────────────────────────────────────────
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"

# Telegram ID администраторов (получают алерты мониторинга)
ADMIN_IDS: list[int] = []

# ──────────────────────────────────────────────────────────────────────────────
# Synology NAS
# ──────────────────────────────────────────────────────────────────────────────
NAS_BASE_URL = "https://YOUR_NAS_HOST:5001/webapi/entry.cgi"
NAS_USER     = "YOUR_NAS_USERNAME"
NAS_PASSWORD = "YOUR_NAS_PASSWORD"
NAS_HTTPS    = True

NAS_ROOT_SHARES = ["/Обмен", "/Днепр"]

# ──────────────────────────────────────────────────────────────────────────────
# База данных
# DB_BACKEND: "sqlite"  — для разработки/тестирования
#             "postgres" — для продакшена
# ──────────────────────────────────────────────────────────────────────────────
DB_BACKEND = "sqlite"   # ← поменяй на "postgres" для продакшена

# SQLite
SQLITE_PATH = str(_ROOT / "dms.db")
SQLITE_DSN  = f"sqlite:///{SQLITE_PATH}"

# PostgreSQL (используется только если DB_BACKEND = "postgres")
PG_HOST     = "localhost"
PG_PORT     = 5432
PG_DB       = "dms"
PG_USER     = "dms_user"
PG_PASS     = "dms_pass_2025"
PG_POOL_SIZE     = 5
PG_MAX_OVERFLOW  = 10
PG_CONN_MAX_AGE  = 60   # секунд (для Django)

# Вычисляемые DSN
if DB_BACKEND == "postgres":
    DB_DSN = f"postgresql+psycopg2://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}"
    DJANGO_DB = {
        "ENGINE":       "django.db.backends.postgresql",
        "NAME":         PG_DB,
        "USER":         PG_USER,
        "PASSWORD":     PG_PASS,
        "HOST":         PG_HOST,
        "PORT":         str(PG_PORT),
        "CONN_MAX_AGE": PG_CONN_MAX_AGE,
    }
else:
    DB_DSN = SQLITE_DSN
    DJANGO_DB = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME":   SQLITE_PATH,
    }

# ──────────────────────────────────────────────────────────────────────────────
# Роли и права
# ──────────────────────────────────────────────────────────────────────────────
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "admin":  ["upload", "find", "approve", "reject", "expiry",
               "finance", "photo_report", "package", "create_object",
               "problems", "search", "my_uploads", "manage_users"],
    "pto":    ["upload", "find", "approve", "reject", "expiry",
               "photo_report", "package", "create_object", "problems",
               "search", "my_uploads"],
    "tb":     ["upload", "find", "approve", "reject", "problems",
               "search", "my_uploads"],
    "buh":    ["upload", "find", "finance", "search", "my_uploads"],
    "prorab": ["upload", "find", "expiry", "photo_report", "problems",
               "search", "my_uploads"],
    "viewer": ["find", "search"],
}

ROLE_LABELS: dict[str, str] = {
    "admin":  "Администратор",
    "pto":    "ПТО",
    "tb":     "ТБ",
    "buh":    "Бухгалтер",
    "prorab": "Прораб",
    "viewer": "Просмотр",
}

# ──────────────────────────────────────────────────────────────────────────────
# Типы документов
# ──────────────────────────────────────────────────────────────────────────────
DOC_TYPES     = ["Сертификат", "ТТН", "Акт", "Протокол", "ФотоОтчет", "Другое"]
FINANCE_TYPES = ["Счета", "ТТН", "Акты", "Договоры", "Прочее"]

FINANCE_TRANSITIONS: dict[str, list[str]] = {
    "черновик":    ["на_проверке"],
    "на_проверке": ["утверждён", "отклонён"],
    "утверждён":   ["оплачен"],
    "отклонён":    ["черновик"],
    "оплачен":     [],
}

# ──────────────────────────────────────────────────────────────────────────────
# Папки объекта на NAS
# ──────────────────────────────────────────────────────────────────────────────
OBJECT_TEMPLATE: list[str] = [
    "_INBOX/Сертификат", "_INBOX/ТТН", "_INBOX/Акт",
    "_INBOX/Протокол", "_INBOX/ФотоОтчет", "_INBOX/Другое",
    "_APPROVED/Сертификат", "_APPROVED/ТТН", "_APPROVED/Акт",
    "_APPROVED/Протокол", "_APPROVED/ФотоОтчет", "_APPROVED/Другое",
    "_REJECTED/Сертификат", "_REJECTED/ТТН", "_REJECTED/Акт",
    "_REJECTED/Протокол", "_REJECTED/Другое",
    "ФотоОтчет", "_PACKAGES",
    "Финансы/_INBOX", "Финансы/Счета", "Финансы/ТТН",
    "Финансы/Акты", "Финансы/Договоры", "Финансы/Прочее",
    "Финансы/_EXPORTS",
]

# ──────────────────────────────────────────────────────────────────────────────
# Планировщик
# ──────────────────────────────────────────────────────────────────────────────
EXPIRY_HOUR   = 9       # напоминания о сроках в 09:00
REMINDER_DAYS = [30, 7, 1]

# ──────────────────────────────────────────────────────────────────────────────
# Белый список Telegram ID (пусто = принимаем всех)
# ──────────────────────────────────────────────────────────────────────────────
WHITELIST: list[int] = []

# ──────────────────────────────────────────────────────────────────────────────
# Чек-лист фотоотчётов по умолчанию
# ──────────────────────────────────────────────────────────────────────────────
DEFAULT_CHECKLIST = [
    "Общий вид объекта",
    "Фундамент / основание",
    "Несущие конструкции",
    "Кровля",
    "Фасад",
    "Внутренние работы",
    "Инженерные системы",
    "Благоустройство",
]

# ──────────────────────────────────────────────────────────────────────────────
# Переопределение из config_local.py (если файл существует)
# Создайте core/config_local.py и задайте там реальные значения:
#   BOT_TOKEN = "реальный_токен"
#   NAS_PASSWORD = "реальный_пароль"
#   DB_BACKEND = "postgres"
#   PG_PASS = "реальный_пароль"
# ──────────────────────────────────────────────────────────────────────────────
try:
    from core.config_local import *   # noqa: F401, F403
    # Пересчитать DSN после переопределения
    if DB_BACKEND == "postgres":
        DB_DSN = f"postgresql+psycopg2://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}"
        DJANGO_DB = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": PG_DB, "USER": PG_USER, "PASSWORD": PG_PASS,
            "HOST": PG_HOST, "PORT": str(PG_PORT), "CONN_MAX_AGE": PG_CONN_MAX_AGE,
        }
    else:
        DB_DSN = f"sqlite:///{SQLITE_PATH}"
        DJANGO_DB = {"ENGINE": "django.db.backends.sqlite3", "NAME": SQLITE_PATH}
except ImportError:
    pass  # config_local.py не обязателен
