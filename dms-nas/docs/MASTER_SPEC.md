# MASTER SPEC — DMS-NAS (Construction)

> Единственный источник правды для всей разработки. Все изменения в продукте должны ссылаться на раздел этого документа.

---

## 1. Цель и результат

Создать единую систему для строительной компании:

- Принимает документы/фото/видео через Telegram
- Хранит файлы структурно на Synology NAS
- Ведёт статусы проверки (approve/reject)
- Ведёт сроки (пропуска, протоколы, поверки) + напоминания
- Ведёт фотоотчёты по чек-листам
- Формирует пакеты документов (ZIP + сводка)
- Ведёт бухгалтерский контур (финдоки + статусы + экспорт)
- Предоставляет Web-панель для таблиц/массовых действий/дашбордов
- Фиксирует аудит всех действий
- Масштабируется на множество объектов
- Имеет резервирование/восстановление
- Готова к OCR/ИИ как следующему слою

---

## 2. Интеграция Synology NAS (DSM File Station API)

### 2.1 Базовые параметры

| Параметр | Значение |
|----------|----------|
| Base URL | `https://stroydnepr.synology.me:5001/webapi/entry.cgi` |
| Transport | HTTPS (self-signed — verify=False) |
| Auth | `SYNO.API.Auth` → `_sid` + `SynoToken` |
| Пути | Логические (`/Днепр`, `/Обмен`), не `/volume1/...` |

> **NON-NEGOTIABLE**: `_sid` и `SynoToken` в query string КАЖДОГО запроса.

### 2.2 Обязательные операции

| API | Версия | Метод |
|-----|--------|-------|
| SYNO.API.Auth | v7 | login / logout |
| SYNO.FileStation.List | v2 | list_share |
| SYNO.FileStation.List | v2 | list |
| SYNO.FileStation.Upload | v3 | upload (multipart, токены в URL) |
| SYNO.FileStation.Download | v2 | download |
| SYNO.FileStation.Delete | v2 | delete |
| SYNO.FileStation.CreateFolder | v2 | create |

### 2.3 Дополнительно

- Copy/Move через `SYNO.FileStation.CopyMove` — если недоступно, fallback: download → upload → delete
- Retry: 1–3 попытки с backoff (1s, 2s)
- Лог каждой NAS операции: `who | action | path | result`

---

## 3. Структура папок на NAS

```
/{Object}/
  _INBOX/
    Сертификат/
    ТТН/
    Акт/
    Протокол/
    ФотоОтчет/
    Другое/
  _APPROVED/ (та же структура типов)
  _REJECTED/ (та же структура типов)
  ФотоОтчет/
  _PACKAGES/
  Финансы/
    _INBOX/
    Счета/
    ТТН/
    Акты/
    Договоры/
    Прочее/
    _EXPORTS/
  Журналы/
  ТБ_ОТ/
```

> `Create Object` обязан создавать ВСЕ папки по этому шаблону.

---

## 4. Роли и доступ

### 4.1 Роли Telegram

| Роль | Доступ |
|------|--------|
| `prorab` | upload, find, photo_report, expiry (свои), problems, my_uploads |
| `pto` | upload, find, approve, reject, packages, problems, expiry (все), search |
| `tb` | upload, find, expiry (все), problems, search |
| `buh` | upload, find, finance, search |
| `admin` | всё + create_object + manage_users |

### 4.2 Web Groups (Django)

| Группа | Доступ |
|--------|--------|
| `admin` | полный доступ, delete allowed |
| `pto` | approve/reject, problems, packages, audit |
| `tb` | expiry manage, audit, docs read |
| `buh` | finance manage, audit |
| `viewer` | read-only + dashboard |

### 4.3 Безопасность

- Telegram: whitelist по `telegram_id` + `is_active`
- Web: Django groups + permissions
- Все критические действия → `audit_log`

---

## 5. База данных (v1 SQLite → v1.1 Postgres)

### 5.1 Таблицы (must-have v1)

| Таблица | Назначение |
|---------|-----------|
| `users` | Telegram пользователи + роли |
| `objects` | Реестр объектов строительства |
| `uploads_log` | Загруженные файлы + статус проверки |
| `expiry_items` | Реестр сроков |
| `reminder_log` | Отправленные напоминания (идемпотентность) |
| `checklists` | Шаблоны чек-листов фотоотчётов |
| `reports` | Сессии фотоотчётов |
| `report_items` | Фото по пунктам чек-листа |
| `packages_log` | История сформированных ZIP |
| `finance_docs` | Финансовые документы |
| `finance_status_log` | История смены статусов финдоков |
| `problems` | Реестр проблем |
| `doc_links` | Связи между сущностями (upload↔finance, upload↔expiry, ...) |
| `audit_log` | Полный журнал всех действий |

### 5.2 Инварианты

- Все сущности содержат `object_name`
- Все действия пользователя содержат `actor_id`
- Все важные события → `audit_log`

### 5.3 Idempotency

| Действие | Гарантия |
|----------|---------|
| Approve | Не повторяется на already approved/rejected |
| Reject | Не повторяется на already rejected |
| Finance status | Строго по `FIN_TRANSITIONS` |
| Reminder | Не дублируется через `reminder_log` |

---

## 6. Acceptance Tests

### A. NAS
- **A1** Login → List shares → List folder → Upload → Verify → Download → Delete
- **A2** Кириллица в путях/именах файлов работает

### B. Telegram: загрузка/поиск
- **B1** Upload → object/type/section → файл на NAS + запись uploads_log
- **B2** Find (browser) → download in chat
- **B3** My uploads today returns correct list

### C. Сроки
- **C1** Add expiry item → appears in "Мои сроки"
- **C2** Scheduler sends T30/T7/T1 once, EXPIRED daily, no duplicates
- **C3** "Обновить документ" marks old archived + sets new record

### D. Approve/Reject
- **D1** Review queue shows new docs
- **D2** Approve: copy to _APPROVED, DB status, notify uploader
- **D3** Reject: ask reason, copy to _REJECTED, DB status+comment, notify uploader

### E. Фотоотчёт
- **E1** Start checklist → create folder → step-by-step → done
- **E2** Filenames 01_... 02_...; summary stored

### F. Packages
- **F1** Builder selects types + period → zip+summary.md on NAS
- **F2** ZIP <50MB sent in Telegram; always saved in _PACKAGES
- **F3** Summary includes counts + burning expiry + photo report status

### G. Problems
- **G1** Mark problem from review card
- **G2** Problems registry lists all by object/status

### H. Finance
- **H1** Add finance doc, stored in /{Object}/Финансы/{Kind}/
- **H2** Status transitions enforced; log each change
- **H3** Export CSV with BOM, saved to _EXPORTS and downloadable

### I. Web Admin
- **I1** Dashboard KPI correct
- **I2** Documents list filters + actions approve/reject work
- **I3** Finance actions + inline log
- **I4** Expiry filters (≤7, ≤1, expired) and actions
- **I5** Audit is read-only
- **I6** NAS proxy download works without direct NAS access
- **I7** Group permissions enforced

### J. Hardening/Prod
- **J1** Web runs via Waitress/Gunicorn, DEBUG=False, allowed hosts set
- **J2** Autostart after reboot documented + working
- **J3** Backup tasks produce artifacts in NAS

### K. Cross-links (Sprint 9)
- **K1** finance_doc linked to upload_log → visible in both admin cards
- **K2** expiry_item linked to upload_log → visible
- **K3** Packages can be created from Web UI; download via proxy

---

## 7. Дорожная карта (Sprints)

| Sprint | Название | Closes |
|--------|---------|--------|
| 1 | NAS client + Bot MVP | A1,A2,B1,B2,B3 |
| 2 | Сроки + напоминания | C1,C2,C3 |
| 3 | Approve/Reject + Problems | D1,D2,D3,G1,G2 |
| 4 | Фотоотчёты | E1,E2 |
| 5 | Packages + Create Object + Search | F1,F2,F3 |
| 6 | Finance | H1,H2,H3 |
| 7 | Web Admin v1 | I1–I7 |
| **8** | **Hardening & Operations** | **J1–J3** |
| **9** | **Cross-links + Packages Web + Object Summary** | **K1–K3** |
| 10 | Migration to Postgres | — |
| 11 | OCR/ИИ | — |

---

## 8. Sprint 8 — Hardening & Operations

### 8.1 Deployment

**Web:**
- Waitress (Windows) / Gunicorn (Linux) as service
- `DEBUG = False`, `ALLOWED_HOSTS` set
- Static files via WhiteNoise
- Optional: Nginx reverse proxy + HTTPS

**Bot:**
- Windows Task Scheduler / systemd autostart
- Auto-restart on crash

**Logs:**
- RotatingFileHandler: `bot.log` 5MB × 5, `web.log` 5MB × 5

### 8.2 Monitoring & Alerts

Notify admins in Telegram when:
- NAS auth fails (repeated, >2 times)
- Package build fails
- Scheduler crash
- DB backup fails

Health endpoint: `GET /health` → JSON `{status, db, nas_status, timestamp}`

### 8.3 Backup & DR

- Daily at 02:00: dump `dms.db` → NAS `/Backup/db/dms_YYYYMMDD.db` (keep 30 days)
- Weekly: full DB export to `/Backup/weekly/`
- Restore: `restore_db.ps1` documented

---

## 9. Sprint 9 — Cross-links + Packages Web + Object Summary

### 9.1 doc_links table

```sql
CREATE TABLE doc_links (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  from_type  TEXT NOT NULL,  -- 'upload','finance_doc','expiry_item','report'
  from_id    INTEGER NOT NULL,
  to_type    TEXT NOT NULL,
  to_id      INTEGER NOT NULL,
  created_by INTEGER,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(from_type, from_id, to_type, to_id)
);
```

UI: в карточке каждой сущности показывать связанные, кнопка Attach/Detach.

### 9.2 Packages from Web

- Custom view `/packages/` с формой: объект + период + типы
- Запускает тот же `core/services/packages.py`
- История пакетов + скачивание через proxy

### 9.3 Object Summary

- Custom view `/objects/<name>/` с агрегатами:
  - Docs count (pending/approved/rejected)
  - Active deadlines
  - Open problems
  - Recent finance docs
  - Last photo report

---

## 10. Sprint 10 — Migration to Postgres

**Trigger:** 5+ concurrent web users или SQLite locks.

**Plan:**
1. Provision Postgres
2. Migration script (sqlite3 → pg_dump compatible)
3. Switch bot + web connection
4. Keep SQLite snapshot as fallback

---

## 11. Sprint 11 — OCR/ИИ (future)

### 11.1 OCR Pipeline
- Отдельный сервис/очередь (Celery + Redis)
- Extract: `doc_number`, `doc_date`, `expiry_date`, `counterparty`, `amount`
- Human-in-the-loop: редактирование + подтверждение

### 11.2 AI Features
- Автотегирование документов
- Черновик "акт входного контроля" из сертификата/ТТН
- Семантический поиск (Qdrant embeddings)
- Requires: GPU server optional

---

## 12. Код-стандарты

### 12.1 Общие правила

- Не дублировать бизнес-логику между bot и web
- Вся логика в `core/services/*`
- NAS access только через `core/nas_client.py`
- Все критические действия → `audit_log`
- Любая новая функция → acceptance test

### 12.2 Формат логов

```
INFO:  user_id={uid} role={role} object={obj} action={action} path={path}
ERROR: {action} failed: {exception} context={...}
```

### 12.3 Как работать с Cursor

Каждый запрос начинай так:

```
Цель: <1-2 предложения>
AT: <acceptance test который должен пройти>
Files: <файлы для изменения>
Constraints: не ломать <список>
```
