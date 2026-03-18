# MASTER SPEC v2 — DMS-NAS (Post-Sprint 9 Roadmap)

> **Baseline**: Sprint 1–9 реализованы. Есть бот + web admin, hardening, мониторинг, бэкапы, doc_links, packages web UI, object summary, objects list.

---

## Главная цель v2

| Направление | Описание |
|---|---|
| **Масштабирование и надёжность** | Postgres, стабильность, роли по объектам, DR/backup, производительность |
| **Сквозная "операционка"** | Единая карточка документа, связи, сводки, массовые операции, отчёты |
| **ИИ-слой (опционально)** | OCR → извлечение полей → автосроки → черновики актов → поиск по смыслу |

---

## 0. NON-NEGOTIABLE правила

- **Никаких паролей/секретов** в публичном репо. Приватный репо / переменные окружения / `bot_config_local.py` в `.gitignore`.
- Все критичные действия **идемпотентны** (approve/reject/status/links/reminders).
- Все изменения данных пишутся в **audit_log**.
- NAS операции **ретраятся** (1–3) и логируются с контекстом (кто/что/куда).
- **Никакой OCR/LLM в request path** — только фоновые задачи (очередь/worker).

---

## Этап 10 — Postgres Migration (Sprint 10) ✅ "на годы"

### Цель
Перевести SQLite → Postgres без потери данных и без простоев, сохранить совместимость bot+web.

### Deliverables
- `docker-compose.pg.yml` (Postgres + pgadmin optional)
- `core/db/postgres.py` (подключение, транзакции)
- `tools/migrate_sqlite_to_pg.py` (миграция данных)
- `tools/verify_migration.py` (проверка counts/hashes)
- Обновление `bot_db.py` и Django settings под Postgres
- Бэкап: `pg_dump` daily/weekly на NAS `/Backup/db_pg/`

### Acceptance Tests (P-серия)
| ID | Сценарий |
|----|----------|
| P1 | bot работает на Postgres (upload/find/approve/expiry/finance/…) |
| P2 | web работает на Postgres (filters/actions/dashboard/nas-proxy) |
| P3 | counts в Postgres == counts SQLite по всем таблицам |
| P4 | миграция повторяемая (idempotent) — повторный запуск не ломает |
| P5 | rollback план: можно вернуться на SQLite snapshot |

### Технические требования
- Таблицы создаются схемой (DDL), не через Django migrations (пока) — controlled schema
- Индексы: `object_name + status` поля (`uploads_log`, `expiry_items`, `finance_docs`, `audit_log`)
- Типы дат: `TIMESTAMP WITH TIME ZONE` (или UTC-строки, единообразно)

---

## Этап 11 — Единый "Document Registry" (Sprint 11) ✅ Реализован

### Цель
Таблица `documents` — один файл = один `doc_id`. Проще связи, поиск, OCR, дедуп, отчёты.

### DB Schema
```sql
CREATE TABLE documents (
    doc_id       BIGSERIAL PRIMARY KEY,
    object_name  TEXT NOT NULL,
    category     TEXT NOT NULL,  -- build|finance|safety|report|other
    type         TEXT,           -- сертификат/ттн/акт/…
    status       TEXT DEFAULT 'new',  -- new|approved|rejected|archived
    nas_path     TEXT,
    file_name    TEXT,
    file_size    BIGINT,
    file_hash_sha256 TEXT,
    created_by_id   BIGINT,
    created_by_name TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);
```

### Acceptance Tests (D-серия)
| ID | Сценарий |
|----|----------|
| D1 | Любой загруженный файл получает `doc_id` |
| D2 | approve/reject изменяет `documents.status` |
| D3 | `finance_doc` ссылается на `doc_id` |
| D4 | links работают через `doc_id` |
| D5 | hash рассчитывается (опционально в фоне) и используется для dedup |

---

## Этап 12 — Object-Level Permissions (Sprint 12) ✅ Реализован

### Цель
Пользователь видит только разрешённые объекты и действия в них.

### DB Schema
```sql
CREATE TABLE user_object_access (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL,
    object_name TEXT NOT NULL,
    role_override TEXT,
    granted_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, object_name)
);
```

### Bot requirements
- menu показывает только allowed objects
- поиск/пакеты/сроки фильтруются по объектам

### Web requirements
- querysets ограничены `allowed_objects`
- viewer видит только свои объекты

### Acceptance Tests (O-серия)
| ID | Сценарий |
|----|----------|
| O1 | user без доступа не видит объект ни в bot, ни в web |
| O2 | попытка открыть URL объекта без доступа → 403 |
| O3 | audit фиксирует "access denied" попытки (опционально) |

---

## Этап 13 — Mass Ops + Quality (Sprint 13) ✅ Реализован

### Цель
Ускорить офисные операции в 5–10 раз.

### Web actions (реализованы)
- Массовое approve/reject
- Массовая смена финансовых статусов
- Массовое привязывание links
- Массовое "пометить проблемой"

### Acceptance Tests (M-серия)
| ID | Сценарий |
|----|----------|
| M1 | Массовый approve 100 документов без таймаута |
| M2 | Массовый status change 200 финдоков без ошибок |
| M3 | Quality dashboard показывает корректные counts |

---

## Этап 14 — DR/Backup "как в банке" (Sprint 14)

### Цель
Полноценный DR — восстановление из бэкапа документировано и проверено.

### Deliverables
- `docs/DR_RUNBOOK.md` (пошагово восстановление)
- `tools/restore_pg.ps1` / `restore_pg.sh`
- Ежемесячный "restore test" (ручной чек-лист)
- Backup verification: size, checksum, latest timestamp

### Acceptance Tests (R-серия)
| ID | Сценарий |
|----|----------|
| R1 | Восстановление базы на тестовый сервер работает |
| R2 | После восстановления bot+web запускаются и показывают данные |
| R3 | Восстановление файлов на NAS не требуется (NAS — источник), ссылки валидны |

---

## Этап 15 — OCR MVP (Sprint 15) ✅ Реализован (MVP)

### Архитектура (реализована)
- `core/services/ocr.py` — движок: pdfplumber + pytesseract
- Фоновый поток (threading.Thread, daemon=True) — **никогда в request path**
- Таблица `ocr_results`: `doc_id, text, fields_json, confidence, created_at`

### UI (реализован)
- Web: OcrResult admin — "OCR fields" блок + кнопки "подтвердить/исправить"
- Bot: уведомление "OCR запущен — результат в веб-панели"
- Auto-create `expiry_items` при подтверждении expires_at

### Acceptance Tests (OCR-серия)
| ID | Сценарий |
|----|----------|
| OCR1 | Документ попадает в фоновый поток → появляется `ocr_results` |
| OCR2 | `expires_at` авто-создаётся при подтверждении |
| OCR3 | Human correction сохраняется в `finance_docs`/`expiry_items` |

---

## Этап 16 — RAG/Поиск по смыслу (Sprint 16) — Будущее

- Embeddings → Qdrant
- Semantic search в web
- "Ответ с источниками" (без галлюцинаций)

---

## Этап 17 — Интеграции (Sprint 17) — По желанию

- Экспорт в 1С/ERP (CSV/API)
- SMTP email уведомления
- SSO/AD (если есть)

---

## Доп. требования к коду (все этапы)

### Стандарты
- Единые логгеры: `bot.log`, `web.log`, `worker.log`
- Единый формат audit событий: `action, entity_type, entity_id, object, details_json`
- Smoke-тесты: `tools/smoke_test.py` (проверка NAS, DB, bot endpoints)

### Commit policy
- Каждый этап → отдельная ветка/PR
- Обновлять `docs/ACCEPTANCE_TESTS.md` и `docs/ARCHITECTURE.md`

---

## Шаблон промпта для Cursor

```
Sprint [N] — [Цель]
Must pass: [A1, A2, A3, ...]
Allowed to modify: [file1, file2, dir/*]
Constraints: не ломать existing features
Add: docs/[relevant_doc].md update
```

**Пример:**
```
Implement Sprint 10 Postgres migration. Must pass P1–P5.
Allowed to modify: bot_db.py, web_admin/settings.py, core/db/*, tools/migrate_sqlite_to_pg.py.
Must keep current features working.
Add docs/DR_RUNBOOK.md draft for rollback.
```

---

## Статус реализации

| Этап | Статус | Спринты |
|------|--------|---------|
| 1–9 | ✅ DONE | Bot + Web + Hardening + Links |
| 10: Postgres | ✅ Code ready, needs switch | `migrate_sqlite_to_postgres.py` |
| 11: Document Registry | ✅ DONE | `documents` table + SHA-256 dedup |
| 12: Object Permissions | ✅ DONE | `user_objects` + `/grant` `/revoke` |
| 13: Mass Ops | ✅ DONE | Bulk approve/reject/finance/links |
| 13: Notifications | ✅ DONE | Web→Telegram approve/reject alerts |
| 13: Weekly digest | ✅ DONE | APScheduler Monday 09:00 |
| 14: PDF Reports | ✅ DONE | ReportLab: dashboard/registry/object |
| 14: Excel Export | ✅ DONE | openpyxl с цветовой кодировкой |
| 15: OCR MVP | ✅ DONE | pdfplumber + human-in-the-loop |
| 14: DR Runbook | 🔲 TODO | `docs/DR_RUNBOOK.md` |
| 16: RAG/Semantic | 🔲 TODO | Qdrant + embeddings |
| 17: 1С/ERP | 🔲 TODO | CSV/API export |
