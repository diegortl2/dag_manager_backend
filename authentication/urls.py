from django.urls import path

from . import views

app_name = "authentication"

urlpatterns = [
    path("me/", views.MeView.as_view(), name="me"),
    path("health/", views.HealthView.as_view(), name="health"),
]
