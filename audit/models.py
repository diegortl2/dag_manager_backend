"""
Audit log model for tracking all significant actions in the DAG Manager.
"""

import uuid

from django.db import models


class AuditLog(models.Model):
    """
    Immutable record of an action performed within the system.
    Every create, update, delete, trigger, pause, and unpause operation
    generates an entry here.
    """

    class Action(models.TextChoices):
        CREATE = "CREATE", "Create"
        UPDATE = "UPDATE", "Update"
        DELETE = "DELETE", "Delete"
        TRIGGER = "TRIGGER", "Trigger"
        PAUSE = "PAUSE", "Pause"
        UNPAUSE = "UNPAUSE", "Unpause"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Azure AD user email or OID who performed the action.",
    )
    action = models.CharField(
        max_length=20,
        choices=Action.choices,
        db_index=True,
    )
    resource_type = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Type of resource acted upon (e.g. 'DAG', 'DAGRun').",
    )
    resource_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Primary key of the affected resource.",
    )
    changes = models.JSONField(
        default=dict,
        blank=True,
        help_text="Before/after snapshot of changed fields.",
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="Client IP address.",
    )
    user_agent = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Client User-Agent header.",
    )

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        indexes = [
            models.Index(fields=["user", "timestamp"]),
            models.Index(fields=["resource_type", "resource_id"]),
        ]

    def __str__(self) -> str:
        return (
            f"[{self.timestamp}] {self.user} {self.action} "
            f"{self.resource_type}:{self.resource_id}"
        )
