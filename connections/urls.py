from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"connections", views.ConnectionViewSet, basename="connection")
router.register(r"dag-connections", views.DAGConnectionViewSet, basename="dagconnection")

app_name = "connections"

urlpatterns = [
    path("", include(router.urls)),
]
