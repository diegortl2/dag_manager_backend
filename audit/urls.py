from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"", views.AuditLogViewSet, basename="auditlog")

app_name = "audit"

urlpatterns = [
    path("", include(router.urls)),
]
