# DMS-NAS — Система управления документами

> Корпоративная система документооборота строительной компании на базе Telegram-бота и Django Web Admin с хранением файлов на Synology NAS.

---

## 📋 Оглавление

- [О проекте](#о-проекте)
- [Стек технологий](#стек-технологий)
- [Архитектура](#архитектура)
- [Функциональность](#функциональность)
- [Скриншоты](#скриншоты)
- [Быстрый старт](#быстрый-старт)
- [Структура проекта](#структура-проекта)
- [Конфигурация](#конфигурация)
- [База данных](#база-данных)

---

## О проекте

**DMS-NAS** — полноценная система управления строительной документацией:

- 📱 **Telegram-бот** для прорабов, ПТО, бухгалтерии и ТБ — загрузка документов прямо из мессенджера
- 🌐 **Django Web Admin** — панель администратора с дашбордом, реестром, OCR, PDF-отчётами
- 🗄️ **Synology NAS** — централизованное хранилище через File Station API
- 🤖 **OCR** — автоматическое распознавание реквизитов документов (номер, дата, сумма, контрагент)

---

## Стек технологий

| Слой | Технология |
|------|-----------|
| Telegram-бот | `python-telegram-bot 20.x` + `APScheduler` |
| Web панель | `Django 5.x` + `django-jazzmin` |
| База данных | **SQLite** (дефолт) / **PostgreSQL** (production) |
| ORM | `SQLAlchemy 2.x` (единый слой для SQLite и PostgreSQL) |
| Хранилище | Synology DSM File Station API |
| OCR | `pdfplumber` + `pytesseract` (опционально) |
| PDF-отчёты | `ReportLab 4.x` |
| Excel-экспорт | `openpyxl` |
| Веб-сервер | `waitress` (Windows) / `gunicorn` (Linux) |
| Статика | `whitenoise` |

---

## Архитектура

```
┌─────────────────────────────────────────────────────────┐
│                    Пользователи Telegram                 │
│   Прораб │ ПТО │ Бухгалтер │ ТБ-специалист │ Директор  │
└──────────────────────┬──────────────────────────────────┘
                       │ Telegram Bot API
┌──────────────────────▼──────────────────────────────────┐
│              apps/bot/bot.py  (python-telegram-bot)      │
│  ┌─────────────────────────────────────────────────┐    │
│  │  ConversationHandlers: Upload │ Find │ Approve  │    │
│  │  Finance │ Expiry │ Photo │ Package │ Problems  │    │
│  │  Grant/Revoke Access │ /grant │ /revoke         │    │
│  └────────────────────┬────────────────────────────┘    │
│                       │                                  │
│  ┌────────────────────▼────────────────────────────┐    │
│  │  core/database.py  (SQLAlchemy)                 │    │
│  │  apps/bot/bot_db.py (CRUD)                      │    │
│  └────────────────────┬────────────────────────────┘    │
│                       │                                  │
│  ┌────────────────────▼────────────────────────────┐    │
│  │  SQLite (dev) │ PostgreSQL (prod via Docker)     │    │
│  └─────────────────────────────────────────────────┘    │
│                       │                                  │
│  ┌────────────────────▼────────────────────────────┐    │
│  │  core/nas_client.py → Synology File Station API │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│             apps/web_admin/  (Django 5)                  │
│  /admin/          — Jazzmin Admin Panel                  │
│  /dashboard/      — KPI Dashboard                        │
│  /pdf/dashboard/  — PDF Management Report                │
│  /pdf/registry/   — PDF Document Registry               │
│  /pdf/object/X/   — PDF Per-Object Report               │
│  /objects/        — Object List                          │
│  /packages/       — Package Builder UI                   │
│  /nas-proxy/      — Secure NAS Download Proxy            │
│  /health          — Health Check                         │
└─────────────────────────────────────────────────────────┘
```

---

## Функциональность

### 📱 Telegram-бот (14 спринтов)

| Модуль | Описание |
|--------|----------|
| **Загрузка документов** | Выбор объекта → тип → загрузка на NAS + реестр |
| **SHA-256 дедупликация** | Автоматическое определение дублей при загрузке |
| **Поиск / Просмотр NAS** | Браузер файлов NAS прямо в боте |
| **Утверждение/Отклонение** | Workflow согласования документов |
| **Сроки документов** | Напоминания о истекающих документах |
| **Фотоотчёты** | Чек-листы с фото по каждому пункту |
| **Финансовые документы** | Счета, акты, накладные с workflow оплаты |
| **Проблемы** | Учёт и отслеживание проблем на объекте |
| **Пакеты документов** | Сборка ZIP-архивов по объекту/периоду |
| **OCR** | Автораспознавание реквизитов загружаемых PDF |
| **Управление доступом** | `/grant`, `/revoke`, `/listaccess` — права по объектам |
| **Уведомления** | Оповещения при approve/reject из Web в Telegram |

### 🌐 Web Admin Panel

| Раздел | Описание |
|--------|----------|
| **Дашборд** | KPI карточки: документы, реестр, сроки, финансы, топ объектов |
| **Реестр документов** | Единая таблица с дедупликацией, категориями, статусами |
| **OCR результаты** | Human-in-the-loop форма для проверки и подтверждения |
| **Финансы** | Статусы: черновик → на проверке → утверждён → оплачен |
| **Сроки** | Контроль дат истечения с цветовой индикацией |
| **Проблемы** | Управление открытыми проблемами |
| **Объекты** | Права доступа пользователей по объектам |
| **PDF-отчёты** | Скачать дашборд / реестр / объект в PDF одним кликом |
| **Excel-экспорт** | Выгрузка реестра в `.xlsx` с цветовой кодировкой |
| **Массовые операции** | Утверждение/отклонение/статус пачками |
| **Журнал аудита** | Полная история всех действий |

---

## Скриншоты

> Web Admin — Дашборд с фирменным стилем, KPI и PDF-экспортом

```
┌────────────────────────────────────────────────────────────┐
│  [Логотип]  ДнепрНАС                          18.03.2026  │
│  Строительная компания Днепр — DMS-NAS                     │
├────────────────────────────────────────────────────────────┤
│  📄 Документы                                              │
│  ┌──────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ ┌──────┐ │
│  │  42  │ │    5     │ │    30    │ │    7    │ │   3  │ │
│  │Всего │ │На провер.│ │Утвержд.  │ │Отклон.  │ │Сегод.│ │
│  └──────┘ └──────────┘ └──────────┘ └─────────┘ └──────┘ │
│  📋 Реестр документов   ⏰ Сроки   💰 Финансы              │
│  🏗️ Топ объектов: ЖК Солнечный · ТРЦ Мега · Офис Центр   │
│  [📊 Дашборд PDF]  [📋 Реестр PDF]                         │
└────────────────────────────────────────────────────────────┘
```

---

## Быстрый старт

### Требования

- Python 3.11+
- Windows 10/11 или Linux
- Synology NAS с включённым File Station API
- Telegram Bot Token (от [@BotFather](https://t.me/botfather))

### Установка (Windows)

```powershell
# 1. Клонировать репозиторий
git clone https://github.com/YOUR_USERNAME/dms-nas.git
cd dms-nas

# 2. Установить все зависимости
.\install_all.ps1

# 3. Настроить конфигурацию
# Отредактировать apps/bot/bot_config.py:
#   TELEGRAM_TOKEN = "ваш_токен"
#   NAS_HOST = "ip_вашего_nas"
#   NAS_USER = "логин"
#   NAS_PASS = "пароль"

# 4. Запустить бота
.\start_bot.ps1

# 5. Запустить веб-панель
cd apps/web_admin
python manage.py migrate
python manage.py createsuperuser
python -m waitress --port=8000 web_admin.wsgi:application
```

### Доступ к панели

```
http://localhost:8000/admin/    — Административная панель
http://localhost:8000/          — Дашборд
http://localhost:8000/health    — Проверка состояния
```

---

## Структура проекта

```
dms-nas/
├── apps/
│   ├── bot/
│   │   ├── bot.py              # Telegram-бот (ConversationHandlers)
│   │   ├── bot_db.py           # CRUD-операции с БД (SQLAlchemy)
│   │   ├── bot_config.py       # Конфигурация (токен, NAS, роли)
│   │   ├── bot_nas.py          # Singleton NAS-клиента
│   │   └── requirements_bot.txt
│   └── web_admin/
│       ├── adminpanel/
│       │   ├── models.py       # Django-модели (managed=False)
│       │   ├── admin.py        # Admin с actions, OCR, PDF, Excel
│       │   ├── views.py        # Дашборд, PDF, NAS-proxy
│       │   ├── urls.py
│       │   ├── templates/      # Кастомные шаблоны
│       │   └── static/         # CSS + логотип
│       ├── web_admin/
│       │   └── settings.py     # Django settings (Jazzmin, DB)
│       └── requirements_web.txt
├── core/
│   ├── database.py             # SQLAlchemy: SQLite/PostgreSQL
│   ├── nas_client.py           # Synology File Station API
│   ├── monitoring.py           # Telegram-алерты для DevOps
│   ├── backup.py               # Резервное копирование на NAS
│   ├── utils.py                # SHA-256, human_size, date utils
│   ├── schema_postgres.sql     # PostgreSQL DDL
│   └── services/
│       ├── approvals.py        # Workflow согласования
│       ├── expiry.py           # Сроки и напоминания
│       ├── finance.py          # Финансовый workflow
│       ├── notify.py           # Web→Telegram уведомления
│       ├── ocr.py              # OCR: pdfplumber + pytesseract
│       ├── packages.py         # ZIP-пакеты документов
│       ├── pdf_report.py       # PDF ReportLab
│       └── reports.py          # Фотоотчёты
├── autostart/
│   ├── install_windows_tasks.ps1  # Windows Task Scheduler
│   └── restore_db.ps1
├── docs/
│   ├── ARCHITECTURE.md
│   ├── ACCEPTANCE_TESTS.md
│   ├── USER_FLOWS.md
│   └── db_schema.md
├── migrate_sqlite_to_postgres.py  # Одноразовая миграция данных
├── docker-compose.yml             # PostgreSQL для production
├── install_all.ps1
└── start_bot.ps1
```

---

## Конфигурация

Все настройки хранятся в `apps/bot/bot_config.py`:

```python
# Telegram
TELEGRAM_TOKEN = "ВАШ_ТОКЕН_БОТА"
ADMIN_IDS      = [123456789]        # Telegram ID администраторов

# Synology NAS
NAS_HOST   = "192.168.1.100"
NAS_PORT   = 5001
NAS_USER   = "dms_user"
NAS_PASS   = "пароль"
NAS_HTTPS  = True

# База данных (sqlite по умолчанию, postgres для production)
DB_MODE = "sqlite"   # или "postgres"

# PostgreSQL (если DB_MODE = "postgres")
POSTGRES_HOST     = "localhost"
POSTGRES_PORT     = 5432
POSTGRES_DB       = "dms"
POSTGRES_USER     = "dms_user"
POSTGRES_PASSWORD = "пароль"
```

---

## База данных

### Таблицы (27 таблиц)

| Таблица | Описание |
|---------|----------|
| `users` | Пользователи Telegram с ролями |
| `user_objects` | Права доступа пользователей к объектам |
| `objects` | Строительные объекты |
| `documents` | Реестр документов (SHA-256, дедупликация) |
| `uploads_log` | Журнал загрузок |
| `expiry_items` | Сроки действия документов |
| `finance_docs` | Финансовые документы |
| `reports` | Фотоотчёты |
| `problems` | Проблемы на объектах |
| `packages_log` | История пакетов |
| `ocr_results` | Результаты OCR-распознавания |
| `doc_links` | Связи между документами |
| `audit_log` | Журнал аудита |

### Миграция на PostgreSQL

```powershell
# 1. Запустить PostgreSQL
docker-compose up -d postgres

# 2. Мигрировать данные
python migrate_sqlite_to_postgres.py

# 3. Переключить режим в bot_config.py
# DB_MODE = "postgres"

# 4. Перезапустить бота и веб
```

---

## Роли пользователей

| Роль | Telegram | Web |
|------|----------|-----|
| `admin` | Все функции + управление пользователями | Полный доступ |
| `pto` | Загрузка, поиск, утверждение, пакеты | Документы, реестр |
| `buh` | Финансовые документы | Финансы |
| `tb` | ТБ-документы, фотоотчёты | Документы ТБ |
| `prorab` | Загрузка, фотоотчёты, проблемы | Только просмотр |
| `viewer` | Поиск и просмотр | Только просмотр |

---

## Лицензия

MIT License — свободное использование для некоммерческих и коммерческих проектов.

---

*Разработано для строительной компании Днепр | DMS-NAS v1.1*
