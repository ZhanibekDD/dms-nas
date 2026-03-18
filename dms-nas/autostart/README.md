# DMS-NAS — Autostart & Operations

## Автозапуск (Windows Task Scheduler)

### Первичная установка

```powershell
# Запустить от имени Администратора
.\autostart\install_windows_tasks.ps1
```

Создаются две задачи:
- **DMS-Bot** — Telegram бот (`start_bot.ps1`)
- **DMS-Web** — Django Web Admin (`apps\web_admin\start_production.ps1`)

Настройки задач:
- Запуск при старте системы + при входе пользователя
- Перезапуск при сбое: 5 попыток × 1 минута

### Управление задачами

```powershell
# Запустить
Start-ScheduledTask -TaskName "DMS-Bot"
Start-ScheduledTask -TaskName "DMS-Web"

# Остановить
Stop-ScheduledTask -TaskName "DMS-Bot"
Stop-ScheduledTask -TaskName "DMS-Web"

# Статус
Get-ScheduledTask -TaskName "DMS-Bot" | Select-Object State
Get-ScheduledTask -TaskName "DMS-Web" | Select-Object State

# Удалить
Unregister-ScheduledTask -TaskName "DMS-Bot" -Confirm:$false
```

---

## Резервное копирование (автоматически)

Bot scheduler выполняет:
- **02:00 ежедневно** — `dms.db` → NAS `/Backup/db/dms_YYYYMMDD.db` (хранится 30 дней)
- **03:00 воскресенье** — `/Backup/weekly/dms_weekly_YYYY_WNN.db`

### Восстановление из бэкапа

```powershell
# Восстановить из конкретного файла
.\autostart\restore_db.ps1 -BackupFile dms_20251231.db
```

Скрипт:
1. Скачивает файл с NAS
2. Останавливает DMS-Bot и DMS-Web
3. Бэкапит текущий dms.db → dms.db.YYYYMMDD_HHMMSS.bak
4. Заменяет dms.db
5. Перезапускает сервисы

---

## Мониторинг

- **Telegram-алерты** → все пользователи с ролью `admin` получают уведомления:
  - NAS недоступен (2+ ошибок подряд)
  - Ошибка резервного копирования
  - Ошибка планировщика
  - Ошибка формирования пакета

- **Health endpoint**: `GET http://localhost:8000/health`
  ```json
  {"status": "ok", "db": "ok", "nas": "ok (3 shares)", "timestamp": "..."}
  ```

---

## Логи

| Файл | Ротация |
|------|---------|
| `dms-nas/bot.log` | 5 МБ × 5 файлов |
| `dms-nas/web.log` | 5 МБ × 5 файлов |

---

## Продакшн Django

```powershell
# Использовать production settings (DEBUG=False)
$env:DJANGO_SETTINGS_MODULE = "web_admin.settings_prod"
python manage.py runserver  # или serve_prod.py
```

---

## Тест бэкапа (проверка раз в месяц)

1. Определить последний файл в NAS `/Backup/db/`
2. Запустить `.\autostart\restore_db.ps1 -BackupFile dms_YYYYMMDD.db` на тест-машине
3. Убедиться что DB открывается: `sqlite3 dms.db ".tables"`
4. Задокументировать дату теста
