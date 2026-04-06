from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"dags", views.DAGViewSet, basename="dag")
router.register(r"runs", views.DAGRunViewSet, basename="dagrun")

app_name = "dags"

urlpatterns = [
    path("", include(router.urls)),
]
