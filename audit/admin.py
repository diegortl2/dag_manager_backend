from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = [
        "timestamp",
        "user",
        "action",
        "resource_type",
        "resource_id",
        "ip_address",
    ]
    list_filter = ["action", "resource_type"]
    search_fields = ["user", "resource_id"]
    readonly_fields = [
        "id",
        "timestamp",
        "user",
        "action",
        "resource_type",
        "resource_id",
        "changes",
        "ip_address",
        "user_agent",
    ]
    ordering = ["-timestamp"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
