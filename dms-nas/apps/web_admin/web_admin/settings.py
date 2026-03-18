"""
Django settings for DMS-NAS web admin panel.
Sprint 10: unified DB config via core.config (единый источник, без .env).
"""

import os
import sys
import pathlib

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent

# Добавляем корень проекта (dms-nas/) в sys.path
_ROOT = str(BASE_DIR.parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Единый источник конфига — core.config
from core.config import SQLITE_PATH as DB_PATH, DJANGO_DB  # noqa: E402

SECRET_KEY = "dms-nas-super-secret-key-change-in-prod-2025"

DEBUG = True

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "adminpanel",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",   # статика без collectstatic
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "web_admin.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "adminpanel" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "web_admin.wsgi.application"

DATABASES = {
    "default": DJANGO_DB   # defined in bot_config.py; switches with DMS_DB_MODE env var
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "ru-RU"
TIME_ZONE = "Europe/Kiev"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "adminpanel" / "static"]

# WhiteNoise — раздача статики напрямую из Django (без nginx)
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Jazzmin theme ──────────────────────────────────────────────────────────────
JAZZMIN_SETTINGS = {
    "site_title":    "ДнепрНАС",
    "site_header":   "ДнепрНАС — Документы",
    "site_brand":    "ДнепрНАС",
    "welcome_sign":  "Добро пожаловать в систему управления документами",
    "copyright":     "© Строительная компания Днепр",

    # ── Логотип компании ──
    "site_logo":        "adminpanel/img/logo.jpg",
    "login_logo":       "adminpanel/img/logo.jpg",
    "login_logo_dark":  "adminpanel/img/logo.jpg",
    "site_logo_classes": "brand-image",
    "site_icon":        "adminpanel/img/favicon.ico",

    "show_sidebar": True,
    "navigation_expanded": True,

    # ── Поиск по сайту ──
    "search_model": ["adminpanel.UploadLog", "adminpanel.Document",
                     "adminpanel.ExpiryItem", "adminpanel.FinanceDoc"],

    # ── Иконки ──
    "icons": {
        "auth":                  "fas fa-users-cog",
        "auth.user":             "fas fa-user",
        "auth.Group":            "fas fa-users",
        "adminpanel.Document":   "fas fa-file-alt",
        "adminpanel.UploadLog":  "fas fa-file-upload",
        "adminpanel.ExpiryItem": "fas fa-clock",
        "adminpanel.FinanceDoc": "fas fa-money-bill-wave",
        "adminpanel.Problem":    "fas fa-exclamation-triangle",
        "adminpanel.AuditLog":   "fas fa-history",
        "adminpanel.PackageLog": "fas fa-box",
        "adminpanel.Report":     "fas fa-camera",
        "adminpanel.UserObject": "fas fa-user-lock",
        "adminpanel.NasObject":  "fas fa-building",
        "adminpanel.DocLink":    "fas fa-link",
        "adminpanel.BotUser":    "fas fa-robot",
        "adminpanel.OcrResult":  "fas fa-eye",
    },

    # ── Порядок в меню ──
    "order_with_respect_to": [
        "adminpanel",
        "adminpanel.NasObject",
        "adminpanel.Document",
        "adminpanel.UploadLog",
        "adminpanel.ExpiryItem",
        "adminpanel.FinanceDoc",
        "adminpanel.Problem",
        "adminpanel.PackageLog",
        "adminpanel.Report",
        "adminpanel.DocLink",
        "adminpanel.OcrResult",
        "adminpanel.UserObject",
        "adminpanel.BotUser",
        "adminpanel.AuditLog",
        "auth",
    ],

    # ── Дополнительные ссылки ──
    "custom_links": {
        "adminpanel": [
            {"name": "📊 Дашборд",        "url": "/dashboard/",  "icon": "fas fa-tachometer-alt"},
            {"name": "📦 Создать пакет",   "url": "/packages/",   "icon": "fas fa-box"},
            {"name": "🏗️ Объекты",         "url": "/objects/",    "icon": "fas fa-building"},
            {"name": "❤️ Health",           "url": "/health",      "icon": "fas fa-heartbeat"},
        ]
    },

    # ── Кастомный CSS ──
    "custom_css": "adminpanel/css/brand.css",

    "changeform_format": "horizontal_tabs",
    "related_modal_active": True,
}

JAZZMIN_UI_TWEAKS = {
    "navbar_small_text":          False,
    "footer_small_text":          True,
    "body_small_text":            False,
    "brand_small_text":           False,
    "brand_colour":               "navbar-dark",
    "accent":                     "accent-warning",
    "navbar":                     "navbar-dark",
    "no_navbar_border":           True,
    "navbar_fixed":               True,
    "layout_boxed":               False,
    "footer_fixed":               False,
    "sidebar_fixed":              True,
    "sidebar":                    "sidebar-dark-warning",
    "sidebar_nav_small_text":     False,
    "sidebar_disable_expand":     False,
    "sidebar_nav_child_indent":   True,
    "sidebar_nav_compact_style":  True,
    "sidebar_nav_legacy_style":   False,
    "sidebar_nav_flat_style":     False,
    "theme":                      "default",
    "dark_mode_theme":            None,
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success",
    },
}

# ── Logging ───────────────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": str(BASE_DIR.parent.parent / "web.log"),
            "encoding": "utf-8",
        },
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {"handlers": ["console", "file"], "level": "INFO"},
}
