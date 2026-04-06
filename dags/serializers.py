"""
DRF serializers for DAG management resources.
"""

from rest_framework import serializers

from .models import DAG, DAGRun, DAGRunLog


class DAGSerializer(serializers.ModelSerializer):
    """Full serializer for DAG CRUD operations."""

    class Meta:
        model = DAG
        fields = [
            "id",
            "dag_id",
            "name",
            "description",
            "python_script",
            "schedule_interval",
            "is_active",
            "max_retries",
            "retry_delay_seconds",
            "timeout_seconds",
            "tags",
            "configuration",
            "owner",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]


class DAGListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for listing DAGs.
    Returns only the most commonly needed fields.
    """

    class Meta:
        model = DAG
        fields = [
            "id",
            "dag_id",
            "name",
            "schedule_interval",
            "is_active",
            "owner",
            "tags",
            "updated_at",
        ]
        read_only_fields = fields


class DAGRunSerializer(serializers.ModelSerializer):
    """Serializer for DAG run records."""

    dag_id = serializers.CharField(source="dag.dag_id", read_only=True)

    class Meta:
        model = DAGRun
        fields = [
            "id",
            "dag",
            "dag_id",
            "run_id",
            "state",
            "execution_date",
            "start_date",
            "end_date",
            "external_trigger",
            "conf",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class DAGRunLogSerializer(serializers.ModelSerializer):
    """Serializer for DAG run log entries."""

    class Meta:
        model = DAGRunLog
        fields = [
            "id",
            "dag_run",
            "timestamp",
            "level",
            "message",
        ]
        read_only_fields = ["id"]


class TriggerDAGRunSerializer(serializers.Serializer):
    """Input serializer for the DAG trigger action."""

    conf = serializers.JSONField(
        required=False,
        default=dict,
        help_text="Optional runtime configuration to pass to the DAG run.",
    )
