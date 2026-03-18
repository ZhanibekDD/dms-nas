-- DMS-NAS PostgreSQL Schema (Sprint 10)
-- Applied automatically by docker-compose via /docker-entrypoint-initdb.d/

-- Users
CREATE TABLE IF NOT EXISTS users (
    id          BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username    TEXT,
    full_name   TEXT,
    role        TEXT    NOT NULL DEFAULT 'viewer',
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- Objects
CREATE TABLE IF NOT EXISTS objects (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    nas_path    TEXT,
    description TEXT,
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_by  BIGINT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- User ↔ Object permissions
CREATE TABLE IF NOT EXISTS user_objects (
    id          BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    object_name TEXT NOT NULL,
    granted_by  BIGINT,
    granted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(telegram_id, object_name)
);
CREATE INDEX IF NOT EXISTS idx_user_objects_tid ON user_objects(telegram_id);

-- Document registry (Sprint 11)
CREATE TABLE IF NOT EXISTS documents (
    id                BIGSERIAL PRIMARY KEY,
    object_name       TEXT NOT NULL,
    category          TEXT NOT NULL DEFAULT 'build',
    doc_type          TEXT,
    status            TEXT NOT NULL DEFAULT 'pending',
    nas_path          TEXT NOT NULL,
    file_hash         TEXT,
    file_size         BIGINT,
    original_filename TEXT,
    created_by        BIGINT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_docs_object ON documents(object_name);
CREATE INDEX IF NOT EXISTS idx_docs_hash   ON documents(file_hash) WHERE file_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_docs_status ON documents(status);

-- Uploads log
CREATE TABLE IF NOT EXISTS uploads_log (
    id            BIGSERIAL PRIMARY KEY,
    telegram_id   BIGINT NOT NULL,
    filename      TEXT,
    nas_path      TEXT,
    doc_type      TEXT,
    object_name   TEXT,
    section       TEXT,
    review_status TEXT NOT NULL DEFAULT 'pending',
    reject_reason TEXT,
    reviewed_by   BIGINT,
    reviewed_at   TIMESTAMPTZ,
    uploaded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tags          TEXT NOT NULL DEFAULT '[]',
    doc_id        BIGINT REFERENCES documents(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_uploads_status  ON uploads_log(review_status);
CREATE INDEX IF NOT EXISTS idx_uploads_object  ON uploads_log(object_name);
CREATE INDEX IF NOT EXISTS idx_uploads_tid     ON uploads_log(telegram_id);
CREATE INDEX IF NOT EXISTS idx_uploads_date    ON uploads_log(uploaded_at DESC);

-- Expiry
CREATE TABLE IF NOT EXISTS expiry_items (
    id          BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    title       TEXT NOT NULL,
    object_name TEXT,
    doc_path    TEXT,
    expires_at  DATE NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_expiry_status ON expiry_items(status);
CREATE INDEX IF NOT EXISTS idx_expiry_date   ON expiry_items(expires_at);

-- Reminder log
CREATE TABLE IF NOT EXISTS reminder_log (
    id          BIGSERIAL PRIMARY KEY,
    expiry_id   BIGINT NOT NULL REFERENCES expiry_items(id) ON DELETE CASCADE,
    days_before INTEGER NOT NULL,
    sent_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_reminder_eid ON reminder_log(expiry_id);

-- Checklists
CREATE TABLE IF NOT EXISTS checklists (
    id         BIGSERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    items      TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Photo reports
CREATE TABLE IF NOT EXISTS reports (
    id           BIGSERIAL PRIMARY KEY,
    telegram_id  BIGINT NOT NULL,
    object_name  TEXT NOT NULL,
    checklist_id BIGINT,
    report_date  DATE,
    nas_folder   TEXT,
    status       TEXT NOT NULL DEFAULT 'in_progress',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_reports_object ON reports(object_name);

CREATE TABLE IF NOT EXISTS report_items (
    id          BIGSERIAL PRIMARY KEY,
    report_id   BIGINT NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    item_index  INTEGER NOT NULL,
    item_name   TEXT NOT NULL,
    nas_path    TEXT,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(report_id, item_index)
);

-- Packages
CREATE TABLE IF NOT EXISTS packages_log (
    id           BIGSERIAL PRIMARY KEY,
    telegram_id  BIGINT NOT NULL,
    object_name  TEXT,
    period       TEXT,
    doc_types    TEXT,
    nas_zip_path TEXT,
    file_count   INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'created',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Finance
CREATE TABLE IF NOT EXISTS finance_docs (
    id           BIGSERIAL PRIMARY KEY,
    telegram_id  BIGINT NOT NULL,
    object_name  TEXT,
    doc_type     TEXT,
    filename     TEXT,
    nas_path     TEXT,
    amount       NUMERIC(15,2),
    counterparty TEXT,
    status       TEXT NOT NULL DEFAULT 'черновик',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    doc_id       BIGINT REFERENCES documents(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_fin_status ON finance_docs(status);
CREATE INDEX IF NOT EXISTS idx_fin_object ON finance_docs(object_name);

CREATE TABLE IF NOT EXISTS finance_status_log (
    id             BIGSERIAL PRIMARY KEY,
    finance_doc_id BIGINT NOT NULL REFERENCES finance_docs(id) ON DELETE CASCADE,
    old_status     TEXT,
    new_status     TEXT,
    changed_by     BIGINT,
    comment        TEXT,
    changed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Problems
CREATE TABLE IF NOT EXISTS problems (
    id          BIGSERIAL PRIMARY KEY,
    upload_id   BIGINT,
    label       TEXT,
    description TEXT,
    status      TEXT NOT NULL DEFAULT 'open',
    created_by  BIGINT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_problems_status ON problems(status);

-- Cross-links (Sprint 9)
CREATE TABLE IF NOT EXISTS doc_links (
    id         BIGSERIAL PRIMARY KEY,
    from_type  TEXT NOT NULL,
    from_id    BIGINT NOT NULL,
    to_type    TEXT NOT NULL,
    to_id      BIGINT NOT NULL,
    created_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(from_type, from_id, to_type, to_id)
);
CREATE INDEX IF NOT EXISTS idx_links_from ON doc_links(from_type, from_id);
CREATE INDEX IF NOT EXISTS idx_links_to   ON doc_links(to_type, to_id);

-- Audit
CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT,
    action      TEXT,
    entity_type TEXT,
    entity_id   BIGINT,
    detail      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_date   ON audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id);

-- Sprint 12: OCR Results
CREATE TABLE IF NOT EXISTS ocr_results (
    id            BIGSERIAL PRIMARY KEY,
    upload_id     BIGINT REFERENCES uploads_log(id) ON DELETE SET NULL,
    doc_id        BIGINT REFERENCES documents(id)   ON DELETE SET NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    doc_number    TEXT,
    doc_date      TEXT,
    expires_at    TEXT,
    counterparty  TEXT,
    amount        NUMERIC(15,2),
    confidence    INTEGER NOT NULL DEFAULT 0,
    raw_text      TEXT,
    reviewed_by   BIGINT,
    reviewed_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ocr_status    ON ocr_results(status);
CREATE INDEX IF NOT EXISTS idx_ocr_upload_id ON ocr_results(upload_id);
CREATE INDEX IF NOT EXISTS idx_ocr_doc_id    ON ocr_results(doc_id);
