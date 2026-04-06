from django.contrib import admin

from .models import DAG, DAGRun, DAGRunLog


@admin.register(DAG)
class DAGAdmin(admin.ModelAdmin):
    list_display = [
        "dag_id",
        "name",
        "is_active",
        "schedule_interval",
        "owner",
        "updated_at",
    ]
    list_filter = ["is_active", "owner"]
    search_fields = ["dag_id", "name", "description"]
    readonly_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]
    ordering = ["-updated_at"]


@admin.register(DAGRun)
class DAGRunAdmin(admin.ModelAdmin):
    list_display = [
        "run_id",
        "dag",
        "state",
        "execution_date",
        "start_date",
        "end_date",
        "external_trigger",
    ]
    list_filter = ["state", "external_trigger"]
    search_fields = ["run_id", "dag__dag_id"]
    readonly_fields = ["id", "created_at"]
    ordering = ["-execution_date"]


@admin.register(DAGRunLog)
class DAGRunLogAdmin(admin.ModelAdmin):
    list_display = ["dag_run", "timestamp", "level", "message_preview"]
    list_filter = ["level"]
    search_fields = ["message"]
    readonly_fields = ["id"]
    ordering = ["-timestamp"]

    @admin.display(description="Message")
    def message_preview(self, obj):
        return obj.message[:120] if obj.message else ""
