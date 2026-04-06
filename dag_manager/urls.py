"""Root URL configuration for dag_manager project."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("dags.urls")),
    path("api/audit/", include("audit.urls")),
    path("api/auth/", include("authentication.urls")),
    path("api/", include("connections.urls")),
]
