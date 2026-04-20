from django.db import models


class DocumentType(models.Model):
    """Справочник типов документов (паспорт, медсправка и т.д.)."""

    code = models.SlugField("код", max_length=64, unique=True)
    name = models.CharField("название", max_length=255)
    description = models.TextField("описание", blank=True)
    sort_order = models.PositiveIntegerField("порядок", default=0)

    class Meta:
        ordering = ["sort_order", "code"]
        verbose_name = "тип документа"
        verbose_name_plural = "типы документов"

    def __str__(self):
        return f"{self.name} ({self.code})"


class Employee(models.Model):
    """Сотрудник в контексте личного дела / pass_docs."""

    employee_code = models.CharField("код сотрудника", max_length=64, unique=True)
    full_name = models.CharField("ФИО", max_length=255)
    profession_key = models.CharField("ключ профессии", max_length=64, db_index=True)
    profession_label = models.CharField("профессия (подпись)", max_length=255, blank=True)
    notes = models.TextField("заметки", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]
        verbose_name = "сотрудник"
        verbose_name_plural = "сотрудники"

    def __str__(self):
        return f"{self.full_name} [{self.employee_code}]"


class EmployeeDocument(models.Model):
    """Факт документа у сотрудника (без файлов и vision на этом этапе)."""

    class Status(models.TextChoices):
        MISSING = "missing", "нет в комплекте"
        PENDING = "pending", "на проверке"
        OK = "ok", "принят"
        EXPIRED = "expired", "просрочен"
        REJECTED = "rejected", "отклонён"

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name="сотрудник",
    )
    document_type = models.ForeignKey(
        DocumentType,
        on_delete=models.CASCADE,
        related_name="employee_documents",
        verbose_name="тип документа",
    )
    status = models.CharField(
        "статус",
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    external_reference = models.CharField(
        "внешний номер / реквизиты",
        max_length=255,
        blank=True,
    )
    valid_until = models.DateField("действителен до", null=True, blank=True)
    metadata = models.JSONField("метаданные импорта", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["employee", "document_type"]
        verbose_name = "документ сотрудника"
        verbose_name_plural = "документы сотрудников"
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "document_type"],
                name="pass_docs_unique_employee_document_type",
            ),
        ]

    def __str__(self):
        return f"{self.employee.employee_code} → {self.document_type.code} ({self.status})"


class ProfessionRequirement(models.Model):
    """Какие типы документов нужны для профессии."""

    profession_key = models.CharField("ключ профессии", max_length=64, db_index=True)
    profession_label = models.CharField("подпись профессии", max_length=255, blank=True)
    document_type = models.ForeignKey(
        DocumentType,
        on_delete=models.CASCADE,
        related_name="profession_requirements",
        verbose_name="тип документа",
    )
    is_required = models.BooleanField("обязателен", default=True)
    notes = models.TextField("заметки", blank=True)

    class Meta:
        ordering = ["profession_key", "document_type"]
        verbose_name = "требование к профессии"
        verbose_name_plural = "требования к профессиям"
        constraints = [
            models.UniqueConstraint(
                fields=["profession_key", "document_type"],
                name="pass_docs_unique_profession_document_type",
            ),
        ]

    def __str__(self):
        req = "обяз." if self.is_required else "опц."
        return f"{self.profession_key} → {self.document_type.code} ({req})"


class PackageRequest(models.Model):
    """Заявка на сборку/отправку пакета (без builder integration)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "черновик"
        SUBMITTED = "submitted", "отправлена"
        READY = "ready", "готова"
        SENT = "sent", "отправлено"
        CANCELLED = "cancelled", "отменена"

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="package_requests",
        verbose_name="сотрудник",
    )
    status = models.CharField(
        "статус",
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    notes = models.TextField("заметки", blank=True)
    meta = models.JSONField("параметры пакета", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "заявка на пакет"
        verbose_name_plural = "заявки на пакеты"

    def __str__(self):
        return f"Пакет {self.id} — {self.employee.employee_code} ({self.status})"
