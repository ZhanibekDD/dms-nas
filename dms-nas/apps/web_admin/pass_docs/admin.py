import json

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    DocumentType,
    Employee,
    EmployeeDocument,
    PackageRequest,
    ProfessionRequirement,
)


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "sort_order",
        "extractor_kind",
        "is_common_document",
        "expiry_rule_days",
    )
    list_filter = ("is_common_document",)
    search_fields = ("code", "name", "description", "extractor_kind")
    ordering = ("sort_order", "code")


class EmployeeDocumentInline(admin.TabularInline):
    model = EmployeeDocument
    extra = 0
    autocomplete_fields = ("document_type",)
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "document_type",
        "source_path",
        "parse_status",
        "status",
        "is_actual",
        "issue_date",
        "expiry_date",
        "created_at",
        "updated_at",
    )


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        "import_key",
        "source_folder_name",
        "employee_code",
        "full_name",
        "last_name",
        "first_name",
        "profession_key",
        "company",
        "is_active",
    )
    list_filter = ("is_active", "profession_key", "company")
    search_fields = (
        "import_key",
        "source_folder_name",
        "source_label",
        "employee_code",
        "full_name",
        "last_name",
        "first_name",
        "middle_name",
        "iin",
        "passport_full_number",
        "company",
    )
    inlines = [EmployeeDocumentInline]
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "import_key",
                    ("source_folder_name", "employee_code"),
                    ("source_prefix", "source_label"),
                    "is_active",
                    "full_name",
                    ("last_name", "first_name", "middle_name"),
                    "profession_key",
                    "profession_label",
                    "company",
                    "birth_date",
                ),
            },
        ),
        (
            "Документы, удостоверяющие личность",
            {
                "fields": (
                    "iin",
                    ("passport_series", "passport_number"),
                    "passport_full_number",
                ),
            },
        ),
        ("Прочее", {"fields": ("notes",)}),
    )


@admin.register(EmployeeDocument)
class EmployeeDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "employee",
        "document_type",
        "display_extractor_kind",
        "parse_status",
        "status",
        "is_actual",
        "issue_date",
        "expiry_date",
        "updated_at",
    )
    list_filter = ("parse_status", "status", "is_actual", "document_type")
    search_fields = (
        "employee__import_key",
        "employee__employee_code",
        "employee__full_name",
        "source_path",
        "external_reference",
    )
    autocomplete_fields = ("employee", "document_type")
    readonly_fields = (
        "created_at",
        "updated_at",
        "normalized_preview",
        "raw_vision_preview",
        "extracted_json_preview",
    )
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "employee",
                    "document_type",
                    "source_path",
                    ("issue_date", "expiry_date"),
                    ("parse_status", "status", "is_actual"),
                    "external_reference",
                    "notes",
                )
            },
        ),
        (
            "Извлечение (просмотр)",
            {
                "description": "Training и прочие типы не синхронизируются в карточку сотрудника автоматически — только хранение здесь.",
                "fields": ("normalized_preview", "raw_vision_preview", "extracted_json_preview"),
            },
        ),
        ("Служебное", {"fields": ("metadata", "created_at", "updated_at")}),
    )

    @admin.display(description="extractor_kind")
    def display_extractor_kind(self, obj) -> str:
        payload = obj.extracted_json or {}
        k = payload.get("extractor_kind") or ""
        return k if k else "—"

    @admin.display(description="normalized (кратко)")
    def normalized_preview(self, obj: EmployeeDocument):
        norm = (obj.extracted_json or {}).get("normalized")
        if not isinstance(norm, dict) or not norm:
            return format_html("<em>нет</em>")
        body = json.dumps(norm, ensure_ascii=False, indent=2)
        return format_html(
            '<pre style="max-height:22em;overflow:auto;white-space:pre-wrap;font-size:12px;margin:0">{}</pre>',
            body,
        )

    @admin.display(description="raw_vision (ответ модели)")
    def raw_vision_preview(self, obj: EmployeeDocument):
        raw = (obj.extracted_json or {}).get("raw_vision")
        if raw is None:
            return format_html("<em>нет</em>")
        if not isinstance(raw, (dict, list)):
            raw = {"value": raw}
        body = json.dumps(raw, ensure_ascii=False, indent=2)
        return format_html(
            '<pre style="max-height:22em;overflow:auto;white-space:pre-wrap;font-size:12px;margin:0">{}</pre>',
            body,
        )

    @admin.display(description="полный extracted_json")
    def extracted_json_preview(self, obj: EmployeeDocument):
        data = obj.extracted_json or {}
        if not data:
            return format_html("<em>пусто</em>")
        body = json.dumps(data, ensure_ascii=False, indent=2)
        return format_html(
            '<pre style="max-height:28em;overflow:auto;white-space:pre-wrap;font-size:11px;margin:0">{}</pre>',
            body,
        )


@admin.register(ProfessionRequirement)
class ProfessionRequirementAdmin(admin.ModelAdmin):
    list_display = (
        "profession_key",
        "document_type",
        "required_for_initial",
        "required_for_renewal",
        "required_for_transport",
    )
    list_filter = (
        "required_for_initial",
        "required_for_renewal",
        "required_for_transport",
        "document_type",
    )
    search_fields = ("profession_key", "profession_label", "notes")
    autocomplete_fields = ("document_type",)


@admin.register(PackageRequest)
class PackageRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "employee",
        "package_kind",
        "status",
        "email_to",
        "created_at",
    )
    list_filter = ("status", "package_kind")
    search_fields = (
        "employee__import_key",
        "employee__employee_code",
        "employee__full_name",
        "email_to",
        "notes",
    )
    autocomplete_fields = ("employee",)
    readonly_fields = ("created_at", "updated_at")
