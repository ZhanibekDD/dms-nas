from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("workspace/dashboard/", views.workspace_dashboard, name="workspace_dashboard"),
    path("workspace/pass-docs/", views.pass_docs_home, name="pass_docs_home"),
    path("workspace/pass-docs/employees/", views.pass_docs_employees, name="pass_docs_employees"),
    path("workspace/pass-docs/documents/", views.pass_docs_documents, name="pass_docs_documents"),
    path("workspace/pass-docs/documents/<int:doc_id>/", views.pass_docs_document_detail, name="pass_docs_document_detail"),
    path("workspace/pass-docs/document-types/", views.pass_docs_document_types, name="pass_docs_document_types"),
    path("workspace/pass-docs/package-requests/", views.pass_docs_package_requests, name="pass_docs_package_requests"),
    path(
        "workspace/pass-docs/package-requests/<int:request_id>/build/",
        views.pass_docs_package_request_build,
        name="pass_docs_package_request_build",
    ),
    path("workspace/employees/", views.workspace_employees, name="workspace_employees"),
    path("workspace/documents/", views.workspace_documents, name="workspace_documents"),
    path("workspace/packages/", views.workspace_packages, name="workspace_packages"),
    path("workspace/ai/", views.ai_assistant_page, name="ai_assistant_page"),
    path("workspace/scan/", views.scan_document_page, name="scan_document_page"),
    path("nas-proxy/", views.nas_proxy, name="nas_proxy"),
    path("health", views.health, name="health"),
    path("packages/", views.packages_ui, name="packages_ui"),
    path("objects/", views.objects_list, name="objects_list"),
    path("objects/<str:object_name>/", views.object_summary, name="object_summary"),
    # Sprint 14: PDF reports
    path("pdf/dashboard/", views.pdf_dashboard, name="pdf_dashboard"),
    path("pdf/registry/",   views.pdf_registry,  name="pdf_registry"),
    path("pdf/object/<str:object_name>/", views.pdf_object, name="pdf_object"),
    # Sprint 13.2: Quality dashboard
    path("quality/", views.quality_dashboard, name="quality_dashboard"),
    # Sprint 11: Document card
    path("doc/<int:doc_id>/", views.document_card, name="document_card"),
    # Sprint 13.1: Reject with reason (AJAX)
    path("reject-with-reason/", views.reject_with_reason, name="reject_with_reason"),
]
