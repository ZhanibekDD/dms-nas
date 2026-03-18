# Database Schema (dms.db — SQLite)

## users
| Column | Type | Notes |
|--------|------|-------|
| telegram_id | INTEGER PK | Telegram user ID |
| username | TEXT | @username (may be empty) |
| full_name | TEXT | Display name |
| role | TEXT | admin / pto / tb / buh / prorab / viewer |
| is_active | INTEGER | 1=active, 0=banned |
| created_at | TEXT | ISO datetime |

## uploads_log
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| telegram_id | INTEGER | Who uploaded |
| filename | TEXT | Original filename |
| nas_path | TEXT | Full logical NAS path |
| doc_type | TEXT | Сертификат/ТТН/Акт/... |
| object_name | TEXT | Construction object |
| section | TEXT | Optional sub-section |
| review_status | TEXT | pending/approved/rejected |
| reject_reason | TEXT | Reason if rejected |
| reviewed_by | INTEGER | Reviewer telegram_id |
| reviewed_at | TEXT | ISO datetime |
| uploaded_at | TEXT | ISO datetime |
| tags | TEXT | JSON array of problem labels |

## expiry_items
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| telegram_id | INTEGER | Owner |
| title | TEXT | Document/deadline name |
| object_name | TEXT | Construction object |
| doc_path | TEXT | Optional NAS path link |
| expires_at | TEXT | YYYY-MM-DD |
| status | TEXT | active/archived |
| created_at | TEXT | |

## reminder_log
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| expiry_id | INTEGER | FK expiry_items |
| days_before | INTEGER | 30/7/1/0(expired) |
| sent_at | TEXT | ISO datetime |

## finance_docs
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| telegram_id | INTEGER | Who created |
| object_name | TEXT | |
| doc_type | TEXT | Счета/ТТН/Акты/Договоры/Прочее |
| filename | TEXT | |
| nas_path | TEXT | |
| amount | REAL | Optional amount in UAH |
| counterparty | TEXT | Contractor/supplier name |
| status | TEXT | черновик/на_проверке/утверждён/отклонён/оплачен |
| created_at | TEXT | |
| updated_at | TEXT | |

## finance_status_log
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| finance_doc_id | INTEGER | FK finance_docs |
| old_status | TEXT | |
| new_status | TEXT | |
| changed_by | INTEGER | telegram_id |
| comment | TEXT | |
| changed_at | TEXT | |

## problems
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| upload_id | INTEGER | Optional FK uploads_log |
| label | TEXT | Tag/category |
| description | TEXT | |
| status | TEXT | open/closed |
| created_by | INTEGER | telegram_id |
| created_at | TEXT | |

## packages_log
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| telegram_id | INTEGER | |
| object_name | TEXT | |
| period | TEXT | e.g. 2025-12 |
| doc_types | TEXT | JSON array |
| nas_zip_path | TEXT | Path to ZIP on NAS |
| file_count | INTEGER | |
| status | TEXT | created |
| created_at | TEXT | |

## reports (photo reports)
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| telegram_id | INTEGER | |
| object_name | TEXT | |
| checklist_id | INTEGER | FK checklists, nullable |
| report_date | TEXT | YYYY-MM-DD |
| nas_folder | TEXT | Target NAS folder |
| status | TEXT | in_progress/done |
| created_at | TEXT | |

## report_items
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| report_id | INTEGER | FK reports |
| item_index | INTEGER | 0-based checklist position |
| item_name | TEXT | Checklist item text |
| nas_path | TEXT | Uploaded photo path |
| uploaded_at | TEXT | |

## checklists
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| name | TEXT | Checklist display name |
| items | TEXT | JSON array of item strings |
| created_at | TEXT | |

## audit_log
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| telegram_id | INTEGER | Actor (null = system) |
| action | TEXT | upload/approve/reject/finance_status/... |
| entity_type | TEXT | upload/finance_doc/object/user/... |
| entity_id | INTEGER | PK of affected entity |
| detail | TEXT | Human-readable context |
| created_at | TEXT | |

## ocr_results (Sprint 12)
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| upload_id | INTEGER FK → uploads_log | Source upload |
| doc_id | INTEGER FK → documents | Source document registry entry |
| status | TEXT | pending / confirmed / rejected |
| doc_number | TEXT | Extracted document number |
| doc_date | TEXT ISO | Extracted document date |
| expires_at | TEXT ISO | Extracted expiry date |
| counterparty | TEXT | Extracted company / person name |
| amount | REAL | Extracted monetary amount |
| confidence | INTEGER | Accuracy score 0–100 |
| raw_text | TEXT | First 2000 chars of extracted text |
| reviewed_by | INTEGER | Telegram ID of reviewer |
| reviewed_at | TEXT | Review timestamp |
| created_at | TEXT | OCR run timestamp |
