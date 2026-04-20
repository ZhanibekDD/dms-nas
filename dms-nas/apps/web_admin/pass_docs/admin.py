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
    list_display = ("code", "name", "sort_order")
    search_fields = ("code", "name")
    ordering = ("sort_order", "code")


class EmployeeDocumentInline(admin.TabularInline):
    model = EmployeeDocument
    extra = 0
    autocomplete_fields = ("document_type",)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("employee_code", "full_name", "profession_key", "updated_at")
    search_fields = ("employee_code", "full_name", "profession_key")
    list_filter = ("profession_key",)
    inlines = [EmployeeDocumentInline]


@admin.register(EmployeeDocument)
class EmployeeDocumentAdmin(admin.ModelAdmin):
    list_display = ("employee", "document_type", "status", "valid_until", "updated_at")
    list_filter = ("status", "document_type")
    search_fields = ("employee__employee_code", "employee__full_name", "external_reference")
    autocomplete_fields = ("employee", "document_type")


@admin.register(ProfessionRequirement)
class ProfessionRequirementAdmin(admin.ModelAdmin):
    list_display = ("profession_key", "document_type", "is_required")
    list_filter = ("is_required", "document_type")
    search_fields = ("profession_key", "profession_label")
    autocomplete_fields = ("document_type",)


@admin.register(PackageRequest)
class PackageRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "employee", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("employee__employee_code", "employee__full_name")
    autocomplete_fields = ("employee",)
