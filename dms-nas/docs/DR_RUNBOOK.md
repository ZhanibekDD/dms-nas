# DR Runbook — DMS-NAS Disaster Recovery

> Документ: пошаговое восстановление системы после сбоя.  
> Время восстановления цели (RTO): 30 минут.  
> Точка восстановления (RPO): последний ночной бэкап (daily 02:00).

---

## Архитектура бэкапов

```
Каждый день в 02:00 (APScheduler в боте):
  dms.db  →  NAS /Backup/db_sqlite/dms_YYYY-MM-DD.db

Каждое воскресенье в 03:00:
  dms.db  →  NAS /Backup/db_weekly/dms_YYYY-MM-DD_weekly.db

Файлы документов:
  Хранятся на NAS → DR не требуется (NAS = источник истины)
```

---

## Сценарий 1: Повреждён/утерян файл dms.db (SQLite)

### Шаг 1 — Остановить бота и веб

```powershell
# Остановить все Python процессы
Get-Process -Name python | Stop-Process -Force
```

### Шаг 2 — Скачать последний бэкап с NAS

```powershell
cd "C:\Users\Администратор\Desktop\DNEPRNAS\dms-nas"

# Укажите дату последнего бэкапа
$date = (Get-Date -Format "yyyy-MM-dd")
$backupFile = "dms_$date.db"

# Скачать через NAS API (или вручную через Synology File Station)
# Путь на NAS: /Backup/db_sqlite/$backupFile
# Скачанный файл сохранить как:
Copy-Item "путь_к_скачанному_файлу\$backupFile" ".\dms.db"
```

### Шаг 3 — Проверить целостность базы

```powershell
.\venv_bot\Scripts\python.exe -c "
import sys; sys.path.insert(0,'.')
from core.database import read_conn
from sqlalchemy import text
with read_conn() as conn:
    tables = conn.execute(text(\"SELECT name FROM sqlite_master WHERE type='table'\")).fetchall()
    print('Tables found:', len(tables))
    count = conn.execute(text('SELECT COUNT(*) FROM uploads_log')).fetchone()[0]
    print('uploads_log rows:', count)
"
```

### Шаг 4 — Запустить бота

```powershell
.\start_bot.ps1
```

### Шаг 5 — Запустить веб

```powershell
cd apps\web_admin
..\..\..\venv_web\Scripts\python.exe -m waitress --port=8000 web_admin.wsgi:application
```

### Шаг 6 — Проверка (R-серия тесты)

```
✅ R1: http://localhost:8000/health → {"status": "ok"}
✅ R2: http://localhost:8000/dashboard/ → данные отображаются
✅ R3: Отправить /menu боту → меню появляется
```

---

## Сценарий 2: Повреждён PostgreSQL (если DB_MODE = "postgres")

### Шаг 1 — Остановить сервисы

```powershell
Get-Process -Name python | Stop-Process -Force
docker-compose stop postgres
```

### Шаг 2 — Восстановить из pg_dump

```powershell
# Скачать последний дамп с NAS (/Backup/db_pg/dms_YYYY-MM-DD.dump)
# Пересоздать базу
docker-compose up -d postgres
Start-Sleep -Seconds 5

docker exec dms-postgres psql -U dms_user -c "DROP DATABASE IF EXISTS dms;"
docker exec dms-postgres psql -U dms_user -c "CREATE DATABASE dms;"
docker exec -i dms-postgres psql -U dms_user dms < dms_YYYY-MM-DD.dump
```

### Шаг 3 — Проверить количество строк

```powershell
.\venv_bot\Scripts\python.exe tools\verify_migration.py
```

### Шаг 4 — Запустить сервисы

```powershell
.\start_bot.ps1
# + запуск веб
```

---

## Сценарий 3: Полная потеря сервера (новая машина)

### Предварительные требования
- Python 3.11+ установлен
- Git установлен
- Docker Desktop установлен (для PostgreSQL)

### Восстановление

```powershell
# 1. Клонировать репозиторий
git clone https://github.com/ZhanibekDD/dms-nas.git
cd dms-nas

# 2. Установить зависимости
.\install_all.ps1

# 3. Восстановить конфигурацию
# Скопировать bot_config_local.py из защищённого хранилища
# ИЛИ вручную заполнить apps/bot/bot_config.py:
#   BOT_TOKEN = "ваш_токен"
#   NAS_BASE_URL = "https://ваш_nas:5001/webapi/entry.cgi"
#   NAS_USER = "логин"
#   NAS_PASSWORD = "пароль"

# 4. Скачать базу данных с NAS (см. Сценарий 1, Шаг 2)

# 5. Запустить
.\start_bot.ps1
cd apps\web_admin
..\..\venv_web\Scripts\python.exe manage.py migrate --run-syncdb
..\..\venv_web\Scripts\python.exe -m waitress --port=8000 web_admin.wsgi:application
```

---

## Ежемесячный чек-лист Restore Test

Выполнять **первое воскресенье каждого месяца**:

```
□ Скачать последний weekly бэкап с NAS (/Backup/db_weekly/)
□ Развернуть на тестовой копии (отдельная папка test_restore/)
□ Запустить: python -c "from apps.bot.bot_db import init_db; init_db()"
□ Проверить: SELECT COUNT(*) FROM uploads_log — сравнить с боевой
□ Проверить: http://localhost:8001/health → "ok"
□ Записать дату проверки в этот файл (строка ниже)
```

### История проверок

| Дата | Результат | Кто проверял |
|------|-----------|--------------|
| — | — | — |

---

## Верификация бэкапов (автоматически)

Бот логирует каждый бэкап:
```
INFO  core.backup  Backup OK: dms_2026-03-18.db (204800 bytes)
```

Если бэкап не прошёл — отправляется алерт в Telegram (core/monitoring.py).

### Ручная проверка последнего бэкапа

```powershell
.\venv_bot\Scripts\python.exe -c "
import sys; sys.path.insert(0,'.')
from apps.bot.bot_nas import get_nas
nas = get_nas()
files = nas.list('/Backup/db_sqlite')
latest = sorted(files, key=lambda x: x.get('time',''))[-1]
print('Latest backup:', latest.get('name'), latest.get('size'), 'bytes')
"
```

---

## Контакты и эскалация

| Роль | Telegram ID | Ответственность |
|------|-------------|-----------------|
| Системный администратор | (добавить) | DB, сервер, бэкапы |
| Технический руководитель | (добавить) | Архитектура, код |

---

*DMS-NAS DR Runbook v1.0 — Строительная компания Днепр*
