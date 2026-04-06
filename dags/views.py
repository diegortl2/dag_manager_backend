"""
DRF ViewSets for DAG management.

Provides full CRUD for DAGs, read-only access to DAG runs and logs, plus
custom actions for triggering, pausing/unpausing, and syncing DAGs to the
on-prem Airflow instance.
"""

import logging
from datetime import datetime, timezone

from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from airflow_client.client import (
    AirflowClient,
    AirflowClientError,
    AirflowConnectionError,
    AirflowNotFoundError,
)
from audit.models import AuditLog

from .models import DAG, DAGRun, DAGRunLog
from .permissions import IsAzureADAuthenticated, IsOwnerOrReadOnly
from .serializers import (
    DAGListSerializer,
    DAGRunLogSerializer,
    DAGRunSerializer,
    DAGSerializer,
    TriggerDAGRunSerializer,
)

logger = logging.getLogger(__name__)


def _get_user_identifier(request) -> str:
    """Extract a stable user identifier from the request for audit fields."""
    user = request.user
    if hasattr(user, "email") and user.email:
        return user.email
    if hasattr(user, "oid") and user.oid:
        return user.oid
    return ""


def _get_client_ip(request) -> str:
    """Best-effort extraction of the client IP address."""
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _create_audit_log(
    request,
    action_name: str,
    resource_type: str,
    resource_id: str,
    changes: dict | None = None,
) -> None:
    """Helper to create an AuditLog entry."""
    AuditLog.objects.create(
        user=_get_user_identifier(request),
        action=action_name,
        resource_type=resource_type,
        resource_id=str(resource_id),
        changes=changes or {},
        ip_address=_get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
    )


def _dag_to_dict(dag: DAG) -> dict:
    """Snapshot a DAG instance to a plain dict for audit change tracking."""
    return {
        "dag_id": dag.dag_id,
        "name": dag.name,
        "description": dag.description,
        "schedule_interval": dag.schedule_interval,
        "is_active": dag.is_active,
        "max_retries": dag.max_retries,
        "retry_delay_seconds": dag.retry_delay_seconds,
        "timeout_seconds": dag.timeout_seconds,
        "tags": dag.tags,
        "configuration": dag.configuration,
        "owner": dag.owner,
    }


class DAGViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for DAG definitions plus custom actions for interacting
    with the Airflow instance.

    list:   GET  /api/dags/
    create: POST /api/dags/
    read:   GET  /api/dags/{id}/
    update: PUT  /api/dags/{id}/
    patch:  PATCH /api/dags/{id}/
    delete: DELETE /api/dags/{id}/

    Custom actions:
        POST /api/dags/{id}/trigger/
        POST /api/dags/{id}/pause/
        POST /api/dags/{id}/unpause/
        POST /api/dags/{id}/sync/
        GET  /api/dags/{id}/runs/
    """

    queryset = DAG.objects.all()
    permission_classes = [IsAzureADAuthenticated, IsOwnerOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        "is_active": ["exact"],
        "owner": ["exact", "icontains"],
    }
    search_fields = ["name", "dag_id", "description"]
    ordering_fields = ["name", "dag_id", "created_at", "updated_at", "owner"]
    ordering = ["-updated_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return DAGListSerializer
        return DAGSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        # Filter by tags (comma-separated query param)
        tags = self.request.query_params.get("tags")
        if tags:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            for tag in tag_list:
                qs = qs.filter(tags__contains=[tag])
        return qs

    # ------------------------------------------------------------------
    # CRUD overrides for audit logging
    # ------------------------------------------------------------------

    def perform_create(self, serializer):
        user_id = _get_user_identifier(self.request)
        dag = serializer.save(created_by=user_id, updated_by=user_id)
        _create_audit_log(
            self.request,
            action_name=AuditLog.Action.CREATE,
            resource_type="DAG",
            resource_id=dag.id,
            changes={"after": _dag_to_dict(dag)},
        )

    def perform_update(self, serializer):
        before = _dag_to_dict(serializer.instance)
        user_id = _get_user_identifier(self.request)
        dag = serializer.save(updated_by=user_id)
        after = _dag_to_dict(dag)
        _create_audit_log(
            self.request,
            action_name=AuditLog.Action.UPDATE,
            resource_type="DAG",
            resource_id=dag.id,
            changes={"before": before, "after": after},
        )

    def perform_destroy(self, instance):
        before = _dag_to_dict(instance)
        dag_id = instance.id
        _create_audit_log(
            self.request,
            action_name=AuditLog.Action.DELETE,
            resource_type="DAG",
            resource_id=dag_id,
            changes={"before": before},
        )
        instance.delete()

    # ------------------------------------------------------------------
    # Custom actions
    # ------------------------------------------------------------------

    @action(detail=True, methods=["post"], url_path="trigger")
    def trigger(self, request, pk=None):
        """Trigger a new DAG run via the Airflow REST API."""
        dag = self.get_object()
        serializer = TriggerDAGRunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        conf = serializer.validated_data.get("conf", {})

        client = AirflowClient()
        try:
            result = client.trigger_dag(dag.dag_id, conf=conf)
        except AirflowNotFoundError:
            return Response(
                {"detail": f"DAG '{dag.dag_id}' not found in Airflow."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except AirflowConnectionError as exc:
            logger.error("Airflow connection error: %s", exc)
            return Response(
                {"detail": "Unable to connect to Airflow.", "error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except AirflowClientError as exc:
            logger.error("Airflow client error: %s", exc)
            return Response(
                {"detail": "Airflow API error.", "error": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Record the run locally
        run = DAGRun.objects.create(
            dag=dag,
            run_id=result.get("dag_run_id", result.get("run_id", "")),
            state=DAGRun.State.QUEUED,
            execution_date=result.get(
                "execution_date", datetime.now(tz=timezone.utc).isoformat()
            ),
            external_trigger=True,
            conf=conf,
        )

        _create_audit_log(
            request,
            action_name=AuditLog.Action.TRIGGER,
            resource_type="DAGRun",
            resource_id=run.id,
            changes={"dag_id": dag.dag_id, "conf": conf},
        )

        return Response(DAGRunSerializer(run).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="pause")
    def pause(self, request, pk=None):
        """Pause the DAG in Airflow and mark it inactive locally."""
        dag = self.get_object()
        before = _dag_to_dict(dag)

        client = AirflowClient()
        try:
            client.pause_dag(dag.dag_id)
        except AirflowConnectionError as exc:
            logger.error("Airflow connection error: %s", exc)
            return Response(
                {"detail": "Unable to connect to Airflow.", "error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except AirflowClientError as exc:
            logger.error("Airflow client error: %s", exc)
            return Response(
                {"detail": "Airflow API error.", "error": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        dag.is_active = False
        dag.updated_by = _get_user_identifier(request)
        dag.save(update_fields=["is_active", "updated_by", "updated_at"])

        after = _dag_to_dict(dag)
        _create_audit_log(
            request,
            action_name=AuditLog.Action.PAUSE,
            resource_type="DAG",
            resource_id=dag.id,
            changes={"before": before, "after": after},
        )

        return Response(DAGSerializer(dag).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="unpause")
    def unpause(self, request, pk=None):
        """Unpause the DAG in Airflow and mark it active locally."""
        dag = self.get_object()
        before = _dag_to_dict(dag)

        client = AirflowClient()
        try:
            client.unpause_dag(dag.dag_id)
        except AirflowConnectionError as exc:
            logger.error("Airflow connection error: %s", exc)
            return Response(
                {"detail": "Unable to connect to Airflow.", "error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except AirflowClientError as exc:
            logger.error("Airflow client error: %s", exc)
            return Response(
                {"detail": "Airflow API error.", "error": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        dag.is_active = True
        dag.updated_by = _get_user_identifier(request)
        dag.save(update_fields=["is_active", "updated_by", "updated_at"])

        after = _dag_to_dict(dag)
        _create_audit_log(
            request,
            action_name=AuditLog.Action.UNPAUSE,
            resource_type="DAG",
            resource_id=dag.id,
            changes={"before": before, "after": after},
        )

        return Response(DAGSerializer(dag).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="sync")
    def sync(self, request, pk=None):
        """Push the DAG definition to Airflow."""
        dag = self.get_object()

        dag_data = {
            "dag_id": dag.dag_id,
            "python_script": dag.python_script,
            "schedule_interval": dag.schedule_interval,
            "is_active": dag.is_active,
            "tags": dag.tags,
            "configuration": dag.configuration,
            "max_retries": dag.max_retries,
            "retry_delay_seconds": dag.retry_delay_seconds,
            "timeout_seconds": dag.timeout_seconds,
        }

        client = AirflowClient()
        try:
            result = client.sync_dag(dag_data)
        except AirflowConnectionError as exc:
            logger.error("Airflow connection error: %s", exc)
            return Response(
                {"detail": "Unable to connect to Airflow.", "error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except AirflowClientError as exc:
            logger.error("Airflow client error: %s", exc)
            return Response(
                {"detail": "Airflow API error.", "error": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {"detail": "DAG synced to Airflow.", "result": result},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"], url_path="runs")
    def runs(self, request, pk=None):
        """List runs for a specific DAG."""
        dag = self.get_object()
        queryset = DAGRun.objects.filter(dag=dag)

        # Filtering
        state = request.query_params.get("state")
        if state:
            queryset = queryset.filter(state=state)

        start_date = request.query_params.get("start_date")
        if start_date:
            queryset = queryset.filter(execution_date__gte=start_date)

        end_date = request.query_params.get("end_date")
        if end_date:
            queryset = queryset.filter(execution_date__lte=end_date)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = DAGRunSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = DAGRunSerializer(queryset, many=True)
        return Response(serializer.data)


class DAGRunViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only access to DAG runs.

    list: GET /api/runs/
    read: GET /api/runs/{id}/

    Custom actions:
        GET /api/runs/{id}/logs/
    """

    queryset = DAGRun.objects.select_related("dag").all()
    serializer_class = DAGRunSerializer
    permission_classes = [IsAzureADAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = {
        "state": ["exact"],
        "dag__dag_id": ["exact"],
        "execution_date": ["gte", "lte"],
        "external_trigger": ["exact"],
    }
    ordering_fields = ["execution_date", "start_date", "end_date", "state", "created_at"]
    ordering = ["-execution_date"]

    @action(detail=True, methods=["get"], url_path="logs")
    def logs(self, request, pk=None):
        """Return log entries for a specific DAG run."""
        dag_run = self.get_object()
        queryset = DAGRunLog.objects.filter(dag_run=dag_run)

        level = request.query_params.get("level")
        if level:
            queryset = queryset.filter(level=level.upper())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = DAGRunLogSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = DAGRunLogSerializer(queryset, many=True)
        return Response(serializer.data)
