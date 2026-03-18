"""
Production settings — import this instead of settings.py in prod.
Set env var: DJANGO_SETTINGS_MODULE=web_admin.settings_prod

Все параметры DB берутся из core.config (без .env).
Для продакшена установи DB_BACKEND = "postgres" в core/config.py
или создай core/config_local.py с нужными значениями.
"""
import sys as _sys
import pathlib as _pathlib

# Убеждаемся, что корень проекта в sys.path (для core.config)
_PROJ_ROOT = str(_pathlib.Path(__file__).resolve().parent.parent.parent.parent)
if _PROJ_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJ_ROOT)

from .settings import *  # noqa: F401,F403

# Импортируем актуальный DJANGO_DB из core.config (перекрывает значение из settings.py)
from core.config import DJANGO_DB  # noqa: E402
DATABASES = {"default": DJANGO_DB}

DEBUG = False

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    # Добавь IP/домен сервера:
    # "192.168.1.100",
    # "dms.example.com",
]

# Для prod: изменить на реальный секрет (можно задать в core/config_local.py)
SECRET_KEY = "dms-nas-CHANGE-THIS-SECRET-KEY-IN-PRODUCTION"

# HTTPS security headers (раскомментировать если есть HTTPS)
# SECURE_HSTS_SECONDS = 3600
# SECURE_SSL_REDIRECT = True
# SESSION_COOKIE_SECURE = True
# CSRF_COOKIE_SECURE = True

# Static files served by WhiteNoise — already configured in settings.py
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Logging overrides for production
from logging.handlers import RotatingFileHandler as _RFH
import pathlib as _pl

_LOG_DIR = _pl.Path(__file__).parent.parent.parent.parent  # dms-nas/

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(_LOG_DIR / "web.log"),
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "encoding": "utf-8",
            "formatter": "standard",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO",
    },
    "loggers": {
        "django.request": {"handlers": ["file"], "level": "WARNING", "propagate": False},
    },
}
