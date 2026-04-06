"""
Read-only ViewSet for querying audit logs with rich filtering.
"""

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets

from dags.permissions import IsAzureADAuthenticated

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only endpoint for audit logs.

    list: GET /api/audit/
    read: GET /api/audit/{id}/

    Supports filtering by:
        - user (exact)
        - action (exact)
        - resource_type (exact)
        - resource_id (exact)
        - timestamp (gte, lte for date-range queries)
    """

    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAzureADAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = {
        "user": ["exact", "icontains"],
        "action": ["exact"],
        "resource_type": ["exact"],
        "resource_id": ["exact"],
        "timestamp": ["gte", "lte"],
    }
    ordering_fields = ["timestamp", "user", "action", "resource_type"]
    ordering = ["-timestamp"]
