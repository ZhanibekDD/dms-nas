"""
Production settings — import this instead of settings.py in prod.
Set env var: DJANGO_SETTINGS_MODULE=web_admin.settings_prod
"""
from .settings import *  # noqa: F401,F403

DEBUG = False

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    # Добавить IP/домен сервера
]

# Для prod: изменить на реальный секрет
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
