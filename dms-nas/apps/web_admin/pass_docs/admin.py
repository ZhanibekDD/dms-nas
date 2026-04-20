from django.contrib import admin

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
                    "employee_code",
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
        "parse_status",
        "status",
        "is_actual",
        "issue_date",
        "expiry_date",
        "updated_at",
    )
    list_filter = ("parse_status", "status", "is_actual", "document_type")
    search_fields = (
        "employee__employee_code",
        "employee__full_name",
        "source_path",
        "external_reference",
    )
    autocomplete_fields = ("employee", "document_type")
    readonly_fields = ("created_at", "updated_at")


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
        "employee__employee_code",
        "employee__full_name",
        "email_to",
        "notes",
    )
    autocomplete_fields = ("employee",)
    readonly_fields = ("created_at", "updated_at")
