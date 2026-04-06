from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    """Read-only serializer for audit log entries."""

    class Meta:
        model = AuditLog
        fields = [
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
        read_only_fields = fields
