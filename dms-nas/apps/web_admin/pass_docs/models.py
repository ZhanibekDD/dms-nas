from django.db import models


class DocumentType(models.Model):
    """Справочник типов документов."""

    code = models.CharField("код", max_length=64, unique=True)
    name = models.CharField("название", max_length=255)
    description = models.TextField("описание", blank=True)
    sort_order = models.PositiveIntegerField("порядок", default=0)
    extractor_kind = models.CharField(
        "тип экстрактора",
        max_length=64,
        blank=True,
        default="",
        help_text="Идентификатор пайплайна извлечения (позже vision и т.д.).",
    )
    is_common_document = models.BooleanField("общий документ", default=False)
    expiry_rule_days = models.PositiveIntegerField(
        "срок действия, дней",
        null=True,
        blank=True,
        help_text="Опциональное правило: через сколько дней истекает документ.",
    )

    class Meta:
        ordering = ["sort_order", "code"]
        verbose_name = "тип документа"
        verbose_name_plural = "типы документов"

    def __str__(self):
        return f"{self.name} ({self.code})"


class Employee(models.Model):
    """Сотрудник (личное дело)."""

    employee_code = models.CharField("код сотрудника", max_length=64, unique=True)
    full_name = models.CharField("ФИО (как в источнике)", max_length=512)
    last_name = models.CharField("фамилия", max_length=128, blank=True)
    first_name = models.CharField("имя", max_length=128, blank=True)
    middle_name = models.CharField("отчество", max_length=128, blank=True)
    profession_key = models.CharField("ключ профессии", max_length=64, blank=True, db_index=True)
    profession_label = models.CharField("профессия (подпись)", max_length=255, blank=True)
    company = models.CharField("организация", max_length=255, blank=True)
    birth_date = models.DateField("дата рождения", null=True, blank=True)
    iin = models.CharField("ИИН/идентификатор", max_length=32, blank=True, db_index=True)
    passport_series = models.CharField("серия паспорта", max_length=16, blank=True)
    passport_number = models.CharField("номер паспорта", max_length=32, blank=True)
    passport_full_number = models.CharField("паспорт полностью", max_length=64, blank=True)
    is_active = models.BooleanField("активен", default=True)
    notes = models.TextField("заметки", blank=True)

    class Meta:
        ordering = ["full_name", "employee_code"]
        verbose_name = "сотрудник"
        verbose_name_plural = "сотрудники"

    def __str__(self):
        return f"{self.full_name} [{self.employee_code}]"


class EmployeeDocument(models.Model):
    """Документ сотрудника (файл на диске + статусы парсинга)."""

    class ParseStatus(models.TextChoices):
        PENDING = "pending", "ожидает разбора"
        SKIPPED = "skipped", "пропущен"
        OK = "ok", "разобран"
        ERROR = "error", "ошибка"

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
    original_file = models.FileField(
        "файл",
        upload_to="pass_docs/uploads/%Y/%m/",
        null=True,
        blank=True,
    )
    source_path = models.TextField("путь к исходному файлу")
    issue_date = models.DateField("дата выдачи", null=True, blank=True)
    expiry_date = models.DateField("срок действия", null=True, blank=True)
    extracted_json = models.JSONField("результат извлечения", default=dict, blank=True)
    parse_status = models.CharField(
        "статус разбора",
        max_length=16,
        choices=ParseStatus.choices,
        default=ParseStatus.PENDING,
    )
    status = models.CharField(
        "статус комплекта",
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    is_actual = models.BooleanField("актуален", default=True)
    external_reference = models.CharField(
        "внешний номер / реквизиты",
        max_length=255,
        blank=True,
    )
    metadata = models.JSONField("метаданные импорта", default=dict, blank=True)
    notes = models.TextField("заметки", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["employee", "document_type", "source_path"]
        verbose_name = "документ сотрудника"
        verbose_name_plural = "документы сотрудников"
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "source_path"],
                name="pass_docs_unique_employee_source_path",
            ),
        ]

    def __str__(self):
        return f"{self.employee.employee_code} → {self.document_type.code} ({self.source_path})"


class ProfessionRequirement(models.Model):
    """Требования к комплекту документов по профессии."""

    profession_key = models.CharField("ключ профессии", max_length=64, db_index=True)
    profession_label = models.CharField("подпись профессии", max_length=255, blank=True)
    document_type = models.ForeignKey(
        DocumentType,
        on_delete=models.CASCADE,
        related_name="profession_requirements",
        verbose_name="тип документа",
    )
    required_for_initial = models.BooleanField("нужен при первичном оформлении", default=True)
    required_for_renewal = models.BooleanField("нужен при продлении", default=True)
    required_for_transport = models.BooleanField("нужен для транспорта", default=False)
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
        return f"{self.profession_key} → {self.document_type.code}"


class PackageRequest(models.Model):
    """Заявка на пакет (без builder / email отправки на этом этапе)."""

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
    package_kind = models.CharField("вид пакета", max_length=64, blank=True)
    status = models.CharField(
        "статус",
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    payload_json = models.JSONField("данные заявки", default=dict, blank=True)
    excel_file = models.FileField(
        "Excel",
        upload_to="pass_docs/packages/%Y/%m/",
        null=True,
        blank=True,
    )
    zip_file = models.FileField(
        "ZIP",
        upload_to="pass_docs/packages/%Y/%m/",
        null=True,
        blank=True,
    )
    email_to = models.CharField("email получателя", max_length=512, blank=True)
    notes = models.TextField("заметки", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "заявка на пакет"
        verbose_name_plural = "заявки на пакеты"

    def __str__(self):
        return f"Пакет {self.id} — {self.employee.employee_code} ({self.status})"
