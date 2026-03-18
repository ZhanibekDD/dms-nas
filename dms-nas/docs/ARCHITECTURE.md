# DMS-NAS Architecture

## Overview

Single-binary-free, NAS-native document management for a construction company.

```
┌─────────────────────────┐     ┌───────────────────────────────┐
│   Telegram Bot           │     │   Django Web Admin             │
│   apps/bot/bot.py        │     │   apps/web_admin/             │
│   (python-telegram-bot)  │     │   (Django 5 + Jazzmin)        │
└────────┬────────────────┘     └──────────┬────────────────────┘
         │                                  │
         ▼                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    core/                                        │
│   nas_client.py  ←  ALL NAS ops via DSM File Station API       │
│   services/                                                     │
│     approvals.py   expiry.py   finance.py                      │
│     packages.py    reports.py                                   │
└─────────────────────────────────────────────────────────────────┘
         │                                  │
         ▼                                  ▼
┌─────────────────────┐     ┌──────────────────────────────────────┐
│   dms.db (SQLite)   │     │   Synology NAS                       │
│   apps/bot/bot_db.py│     │   https://stroydnepr.synology.me:5001│
│                     │     │   SYNO.FileStation.*                 │
└─────────────────────┘     └──────────────────────────────────────┘
```

## Components

### core/nas_client.py
- Thread-safe Synology DSM File Station client
- Auto-retry (3 attempts) with exponential backoff
- Handles login/logout/relogin transparently
- Methods: login, list_shares, list_folder, create_folder, upload, download, delete, copy_move, rename

### core/services/
| File | Responsibility |
|------|----------------|
| approvals.py | approve_doc / reject_doc — idempotent NAS copy + DB update |
| expiry.py | Daily reminder dispatch (T-30/T-7/T-1/Expired) |
| finance.py | Status transition matrix + CSV export |
| packages.py | ZIP builder from NAS files + summary.md |
| reports.py | Photo report workflow + create_object_structure |

### apps/bot/
| File | Responsibility |
|------|----------------|
| bot_config.py | All config/credentials — single source of truth |
| bot_db.py | SQLite CRUD layer |
| bot_nas.py | Singleton NASClient wrapper for bot |
| bot.py | All Telegram conversation handlers (Sprints 1–7) |

### apps/web_admin/
| File | Responsibility |
|------|----------------|
| settings.py | Django config, Jazzmin theme, shared DB path |
| adminpanel/models.py | managed=False models mapped to bot's SQLite |
| adminpanel/admin.py | Rich admin with actions, filters, download links |
| adminpanel/views.py | Dashboard KPI + NAS download proxy |

## Data Flow — Upload

```
User sends file in Telegram
  → bot.py: upload_got_file()
  → bot_nas.py: nas_upload(dest_folder, filename, bytes)
  → core/nas_client.py: upload()  [multipart POST, tokens in URL]
  → NAS stores file at /{Object}/_INBOX/{Type}/filename
  → bot_db.py: log_upload()  [record in uploads_log]
  → audit log entry
```

## Data Flow — Approve (web or bot)

```
Reviewer clicks Approve
  → core/services/approvals.py: approve_doc(db, nas, upload_id, reviewer_id)
  → Idempotency check: already approved? return ok
  → nas_client.py: copy_move(src _INBOX path, dest _APPROVED folder)
  → bot_db.py: set_review_status('approved')
  → bot_db.py: audit(...)
  → bot notifies uploader
```

## Database Schema (dms.db)

| Table | Purpose |
|-------|---------|
| users | Telegram users + roles |
| uploads_log | Every uploaded file + review status |
| expiry_items | Deadline registry |
| reminder_log | Sent reminders (idempotency) |
| checklists | Photo report checklists |
| reports | Photo report sessions |
| report_items | Per-item photos within a report |
| packages_log | Generated ZIP packages |
| finance_docs | Financial documents + status |
| finance_status_log | Full status change history |
| problems | Problem registry with labels |
| audit_log | All mutations (user, action, entity) |

## NAS Path Convention

```
/{ObjectName}/
  _INBOX/
    Сертификат/   — newly uploaded
    ТТН/
    Акт/
    Протокол/
    ФотоОтчет/
    Другое/
  _APPROVED/      — approved copies
  _REJECTED/      — rejected copies
  ФотоОтчет/      — structured photo reports
  _PACKAGES/      — generated ZIP packages
  Финансы/
    _INBOX/
    Счета/ ТТН/ Акты/ Договоры/ Прочее/
    _EXPORTS/
```

## Finance Status Machine

```
черновик → на_проверке → утверждён → оплачен
                       ↘ отклонён → черновик
```

Role permissions per transition are enforced in `core/services/finance.py`.
