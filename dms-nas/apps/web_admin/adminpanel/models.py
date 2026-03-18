"""
Django models — managed=False, mapped to the DB schema (SQLite or Postgres).
Sprint 10: added Document, UserObject models.
No migrations needed for bot-owned tables.
"""

from django.db import models


CATEGORY_CHOICES = [
    ("build",   "Строительство"),
    ("finance", "Финансы"),
    ("safety",  "ТБ/ОТ"),
    ("photo",   "Фото"),
    ("other",   "Прочее"),
]

DOC_STATUS_CHOICES = [
    ("pending",  "На проверке"),
    ("approved", "Утверждён"),
    ("rejected", "Отклонён"),
    ("archived", "Архив"),
]


# ─── Sprint 11: Document Registry ────────────────────────────────────────────

class Document(models.Model):
    id                = models.AutoField(primary_key=True)
    object_name       = models.TextField()
    category          = models.TextField(choices=CATEGORY_CHOICES, default="build")
    doc_type          = models.TextField(blank=True)
    status            = models.TextField(choices=DOC_STATUS_CHOICES, default="pending")
    nas_path          = models.TextField()
    file_hash         = models.TextField(blank=True, null=True)
    file_size         = models.BigIntegerField(null=True, blank=True)
    original_filename = models.TextField(blank=True)
    created_by        = models.BigIntegerField(null=True, blank=True)
    created_at        = models.TextField()
    updated_at        = models.TextField()

    class Meta:
        managed  = False
        db_table = "documents"
        verbose_name        = "Документ (реестр)"
        verbose_name_plural = "Реестр документов"
        ordering = ["-id"]

    def __str__(self):
        return f"{self.original_filename} [{self.object_name}/{self.doc_type}]"


# ─── User ↔ Object permissions ────────────────────────────────────────────────

class UserObject(models.Model):
    id          = models.AutoField(primary_key=True)
    telegram_id = models.BigIntegerField()
    object_name = models.TextField()
    granted_by  = models.BigIntegerField(null=True, blank=True)
    granted_at  = models.TextField()

    class Meta:
        managed  = False
        db_table = "user_objects"
        verbose_name        = "Доступ к объекту"
        verbose_name_plural = "Доступы к объектам"
        ordering = ["telegram_id", "object_name"]
        unique_together = [("telegram_id", "object_name")]

    def __str__(self):
        return f"User {self.telegram_id} → {self.object_name}"


class BotUser(models.Model):
    telegram_id = models.BigIntegerField(primary_key=True)
    username    = models.TextField(blank=True)
    full_name   = models.TextField(blank=True)
    role        = models.TextField(default="viewer")
    is_active   = models.BooleanField(default=True)
    created_at  = models.TextField()

    class Meta:
        managed  = False
        db_table = "users"
        verbose_name        = "Пользователь бота"
        verbose_name_plural = "Пользователи бота"

    def __str__(self):
        return f"{self.full_name} ({self.role})"


class UploadLog(models.Model):
    id            = models.AutoField(primary_key=True)
    telegram_id   = models.BigIntegerField()
    filename      = models.TextField(blank=True)
    nas_path      = models.TextField(blank=True)
    doc_type      = models.TextField(blank=True)
    object_name   = models.TextField(blank=True)
    section       = models.TextField(blank=True)
    review_status = models.TextField(default="pending")
    reject_reason = models.TextField(blank=True, null=True)
    reviewed_by   = models.BigIntegerField(null=True, blank=True)
    reviewed_at   = models.TextField(null=True, blank=True)
    uploaded_at   = models.TextField()
    tags          = models.TextField(default="[]")
    doc_id        = models.BigIntegerField(null=True, blank=True)

    class Meta:
        managed  = False
        db_table = "uploads_log"
        verbose_name        = "Документ"
        verbose_name_plural = "Документы"
        ordering = ["-id"]

    def __str__(self):
        return f"{self.filename} ({self.object_name})"


class ExpiryItem(models.Model):
    id          = models.AutoField(primary_key=True)
    telegram_id = models.BigIntegerField()
    title       = models.TextField()
    object_name = models.TextField(blank=True)
    doc_path    = models.TextField(blank=True)
    expires_at  = models.TextField()
    status      = models.TextField(default="active")
    created_at  = models.TextField()

    class Meta:
        managed  = False
        db_table = "expiry_items"
        verbose_name        = "Срок"
        verbose_name_plural = "Сроки"
        ordering = ["expires_at"]

    def __str__(self):
        return f"{self.title} [{self.expires_at}]"


class FinanceDoc(models.Model):
    id           = models.AutoField(primary_key=True)
    telegram_id  = models.BigIntegerField()
    object_name  = models.TextField(blank=True)
    doc_type     = models.TextField(blank=True)
    filename     = models.TextField(blank=True)
    nas_path     = models.TextField(blank=True)
    amount       = models.FloatField(null=True, blank=True)
    counterparty = models.TextField(blank=True)
    status       = models.TextField(default="черновик")
    created_at   = models.TextField()
    updated_at   = models.TextField()
    doc_id       = models.BigIntegerField(null=True, blank=True)

    class Meta:
        managed  = False
        db_table = "finance_docs"
        verbose_name        = "Финдокумент"
        verbose_name_plural = "Финансы"
        ordering = ["-id"]

    def __str__(self):
        return f"{self.filename} [{self.status}]"


class FinanceStatusLog(models.Model):
    id             = models.AutoField(primary_key=True)
    finance_doc_id = models.IntegerField()
    old_status     = models.TextField(blank=True)
    new_status     = models.TextField(blank=True)
    changed_by     = models.BigIntegerField(null=True, blank=True)
    comment        = models.TextField(blank=True)
    changed_at     = models.TextField()

    class Meta:
        managed  = False
        db_table = "finance_status_log"
        verbose_name        = "История статуса финдока"
        verbose_name_plural = "История статусов финдоков"
        ordering = ["-id"]


class Problem(models.Model):
    id          = models.AutoField(primary_key=True)
    upload_id   = models.IntegerField(null=True, blank=True)
    label       = models.TextField(blank=True)
    description = models.TextField(blank=True)
    status      = models.TextField(default="open")
    created_by  = models.BigIntegerField()
    created_at  = models.TextField()

    class Meta:
        managed  = False
        db_table = "problems"
        verbose_name        = "Проблема"
        verbose_name_plural = "Проблемы"
        ordering = ["-id"]

    def __str__(self):
        return f"[{self.label}] {self.description[:50]}"


class PackageLog(models.Model):
    id           = models.AutoField(primary_key=True)
    telegram_id  = models.BigIntegerField()
    object_name  = models.TextField(blank=True)
    period       = models.TextField(blank=True)
    doc_types    = models.TextField(blank=True)
    nas_zip_path = models.TextField(blank=True)
    file_count   = models.IntegerField(default=0)
    status       = models.TextField(default="created")
    created_at   = models.TextField()

    class Meta:
        managed  = False
        db_table = "packages_log"
        verbose_name        = "Пакет"
        verbose_name_plural = "Пакеты"
        ordering = ["-id"]

    def __str__(self):
        return f"{self.object_name} {self.period} ({self.file_count} файлов)"


class Report(models.Model):
    id           = models.AutoField(primary_key=True)
    telegram_id  = models.BigIntegerField()
    object_name  = models.TextField()
    checklist_id = models.IntegerField(null=True, blank=True)
    report_date  = models.TextField(blank=True)
    nas_folder   = models.TextField(blank=True)
    status       = models.TextField(default="in_progress")
    created_at   = models.TextField()

    class Meta:
        managed  = False
        db_table = "reports"
        verbose_name        = "Фотоотчёт"
        verbose_name_plural = "Фотоотчёты"
        ordering = ["-id"]

    def __str__(self):
        return f"{self.object_name} {self.report_date}"


class DocLink(models.Model):
    id         = models.AutoField(primary_key=True)
    from_type  = models.TextField()
    from_id    = models.IntegerField()
    to_type    = models.TextField()
    to_id      = models.IntegerField()
    created_by = models.BigIntegerField(null=True, blank=True)
    created_at = models.TextField()

    class Meta:
        managed  = False
        db_table = "doc_links"
        verbose_name        = "Связь"
        verbose_name_plural = "Связи документов"
        ordering = ["-id"]

    def __str__(self):
        return f"{self.from_type}#{self.from_id} → {self.to_type}#{self.to_id}"


class NasObject(models.Model):
    id          = models.AutoField(primary_key=True)
    name        = models.TextField(unique=True)
    nas_path    = models.TextField(blank=True)
    description = models.TextField(blank=True)
    is_active   = models.BooleanField(default=True)
    created_by  = models.BigIntegerField(null=True, blank=True)
    created_at  = models.TextField()

    class Meta:
        managed  = False
        db_table = "objects"
        verbose_name        = "Объект"
        verbose_name_plural = "Объекты"
        ordering = ["name"]

    def __str__(self):
        return self.name


class AuditLog(models.Model):
    id          = models.AutoField(primary_key=True)
    telegram_id = models.BigIntegerField(null=True, blank=True)
    action      = models.TextField(blank=True)
    entity_type = models.TextField(blank=True)
    entity_id   = models.IntegerField(null=True, blank=True)
    detail      = models.TextField(blank=True)
    created_at  = models.TextField()

    class Meta:
        managed  = False
        db_table = "audit_log"
        verbose_name        = "Аудит"
        verbose_name_plural = "Журнал аудита"
        ordering = ["-id"]

    def __str__(self):
        return f"{self.action} {self.entity_type}#{self.entity_id}"


# ─── Sprint 12: OCR Results ───────────────────────────────────────────────────

OCR_STATUS_CHOICES = [
    ("pending",   "Ожидает проверки"),
    ("confirmed", "Подтверждено"),
    ("rejected",  "Отклонено"),
]


class OcrResult(models.Model):
    id           = models.AutoField(primary_key=True)
    upload_id    = models.IntegerField(null=True, blank=True)
    doc_id       = models.IntegerField(null=True, blank=True)
    status       = models.TextField(default="pending", choices=OCR_STATUS_CHOICES)
    doc_number   = models.TextField(blank=True, null=True)
    doc_date     = models.TextField(blank=True, null=True)
    expires_at   = models.TextField(blank=True, null=True)
    counterparty = models.TextField(blank=True, null=True)
    amount       = models.FloatField(null=True, blank=True)
    confidence   = models.IntegerField(default=0)
    raw_text     = models.TextField(blank=True)
    reviewed_by  = models.BigIntegerField(null=True, blank=True)
    reviewed_at  = models.TextField(blank=True, null=True)
    created_at   = models.TextField()

    class Meta:
        managed  = False
        db_table = "ocr_results"
        verbose_name        = "OCR результат"
        verbose_name_plural = "OCR результаты"
        ordering = ["-id"]

    def __str__(self):
        return f"OCR #{self.id} — {self.status} ({self.confidence}%)"
