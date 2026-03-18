"""
Central configuration — all tokens / credentials stored here.
"""

# ── Telegram ──────────────────────────────────────────────────────────────────
BOT_TOKEN = "7954883438:AAFNTTNkO6Vy_J3-eb2yJQTft0DcZ3I7f6A"

# ── Synology NAS ──────────────────────────────────────────────────────────────
NAS_BASE_URL = "https://stroydnepr.synology.me:5001/webapi/entry.cgi"
NAS_USER     = "Administrator"
NAS_PASSWORD = "Lytgh8989."

# ── Database ──────────────────────────────────────────────────────────────────
import pathlib
_HERE = pathlib.Path(__file__).parent
DB_PATH = str(_HERE.parent.parent / "dms.db")

# DB_MODE: 'sqlite' (default) or 'postgres'
# Поменяй на 'postgres' после запуска migrate_sqlite_to_postgres.py
DB_MODE = "sqlite"

# SQLite DSN
DB_DSN_SQLITE = f"sqlite:///{DB_PATH}"

# PostgreSQL — всё прямо в коде (no .env)
POSTGRES_HOST     = "localhost"
POSTGRES_PORT     = 5432
POSTGRES_DB       = "dms"
POSTGRES_USER     = "dms_user"
POSTGRES_PASSWORD = "dms_pass_2025"

# Вычисляемый DSN (используется core/database.py и Django)
if DB_MODE == "postgres":
    DB_DSN = (
        f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )
    DJANGO_DB = {
        "ENGINE":   "django.db.backends.postgresql",
        "NAME":     POSTGRES_DB,
        "USER":     POSTGRES_USER,
        "PASSWORD": POSTGRES_PASSWORD,
        "HOST":     POSTGRES_HOST,
        "PORT":     str(POSTGRES_PORT),
        "CONN_MAX_AGE": 60,
    }
else:
    DB_DSN = DB_DSN_SQLITE
    DJANGO_DB = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME":   DB_PATH,
    }

# ── Roles & permissions ───────────────────────────────────────────────────────
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

# ── Document types ────────────────────────────────────────────────────────────
DOC_TYPES      = ["Сертификат", "ТТН", "Акт", "Протокол", "ФотоОтчет", "Другое"]
FINANCE_TYPES  = ["Счета", "ТТН", "Акты", "Договоры", "Прочее"]

# ── Finance status transitions ────────────────────────────────────────────────
FINANCE_TRANSITIONS: dict[str, list[str]] = {
    "черновик":    ["на_проверке"],
    "на_проверке": ["утверждён", "отклонён"],
    "утверждён":   ["оплачен"],
    "отклонён":    ["черновик"],
    "оплачен":     [],
}

# ── Object folder template ─────────────────────────────────────────────────────
OBJECT_TEMPLATE: list[str] = [
    "_INBOX/Сертификат",
    "_INBOX/ТТН",
    "_INBOX/Акт",
    "_INBOX/Протокол",
    "_INBOX/ФотоОтчет",
    "_INBOX/Другое",
    "_APPROVED/Сертификат",
    "_APPROVED/ТТН",
    "_APPROVED/Акт",
    "_APPROVED/Протокол",
    "_APPROVED/ФотоОтчет",
    "_APPROVED/Другое",
    "_REJECTED/Сертификат",
    "_REJECTED/ТТН",
    "_REJECTED/Акт",
    "_REJECTED/Протокол",
    "_REJECTED/Другое",
    "ФотоОтчет",
    "_PACKAGES",
    "Финансы/_INBOX",
    "Финансы/Счета",
    "Финансы/ТТН",
    "Финансы/Акты",
    "Финансы/Договоры",
    "Финансы/Прочее",
    "Финансы/_EXPORTS",
]

# ── Scheduler ─────────────────────────────────────────────────────────────────
EXPIRY_HOUR   = 9    # daily reminder at 09:00
REMINDER_DAYS = [30, 7, 1]

# ── Whitelist: Telegram IDs allowed to use the bot ────────────────────────────
# Empty = all users can register (admin must confirm role assignment)
WHITELIST: list[int] = []

# ── Default checklist for photo reports ──────────────────────────────────────
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

# ── NAS root shares to expose in browser ──────────────────────────────────────
NAS_ROOT_SHARES = ["/Обмен", "/Днепр"]
