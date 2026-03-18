from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("nas-proxy/", views.nas_proxy, name="nas_proxy"),
    path("health", views.health, name="health"),
    path("packages/", views.packages_ui, name="packages_ui"),
    path("objects/", views.objects_list, name="objects_list"),
    path("objects/<str:object_name>/", views.object_summary, name="object_summary"),
    # Sprint 14: PDF reports
    path("pdf/dashboard/", views.pdf_dashboard, name="pdf_dashboard"),
    path("pdf/registry/",   views.pdf_registry,  name="pdf_registry"),
    path("pdf/object/<str:object_name>/", views.pdf_object, name="pdf_object"),
]
