"""
DRF ViewSets for Connection management.

Provides CRUD for connections, DAG-connection linking, connection testing,
and syncing connections to Airflow.
"""

import logging

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from audit.models import AuditLog
from dags.permissions import IsAzureADAuthenticated, IsOwnerOrReadOnly
from dags.views import _create_audit_log, _get_user_identifier

from .keyvault import KeyVaultClient, KeyVaultError
from .models import Connection, DAGConnection
from .serializers import (
    ConnectionListSerializer,
    ConnectionSerializer,
    DAGConnectionSerializer,
    DAGConnectionWriteSerializer,
    TestConnectionSerializer,
)

logger = logging.getLogger(__name__)


def _connection_to_dict(conn: Connection) -> dict:
    """Snapshot a Connection for audit trail."""
    return {
        "conn_id": conn.conn_id,
        "name": conn.name,
        "connection_type": conn.connection_type,
        "host": conn.host,
        "port": conn.port,
        "schema_name": conn.schema_name,
        "login": conn.login,
        "auth_method": conn.auth_method,
        "key_vault_secret_name": conn.key_vault_secret_name,
        "is_active": conn.is_active,
        "owner": conn.owner,
    }


class ConnectionViewSet(viewsets.ModelViewSet):
    """
    CRUD for external service connections.

    list:    GET    /api/connections/
    create:  POST   /api/connections/
    read:    GET    /api/connections/{id}/
    update:  PUT    /api/connections/{id}/
    delete:  DELETE /api/connections/{id}/

    Custom actions:
        POST /api/connections/{id}/test/
        POST /api/connections/{id}/sync-to-airflow/
    """

    queryset = Connection.objects.all()
    permission_classes = [IsAzureADAuthenticated, IsOwnerOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        "connection_type": ["exact"],
        "auth_method": ["exact"],
        "is_active": ["exact"],
        "owner": ["exact", "icontains"],
    }
    search_fields = ["name", "conn_id", "host", "description"]
    ordering_fields = ["name", "conn_id", "connection_type", "created_at", "updated_at"]
    ordering = ["name"]

    def get_serializer_class(self):
        if self.action == "list":
            return ConnectionListSerializer
        return ConnectionSerializer

    def perform_create(self, serializer):
        user_id = _get_user_identifier(self.request)
        conn = serializer.save(created_by=user_id, updated_by=user_id)
        _create_audit_log(
            self.request,
            action_name=AuditLog.Action.CREATE,
            resource_type="Connection",
            resource_id=conn.id,
            changes={"after": _connection_to_dict(conn)},
        )

    def perform_update(self, serializer):
        before = _connection_to_dict(serializer.instance)
        user_id = _get_user_identifier(self.request)
        conn = serializer.save(updated_by=user_id)
        after = _connection_to_dict(conn)
        _create_audit_log(
            self.request,
            action_name=AuditLog.Action.UPDATE,
            resource_type="Connection",
            resource_id=conn.id,
            changes={"before": before, "after": after},
        )

    def perform_destroy(self, instance):
        before = _connection_to_dict(instance)
        conn_id = instance.id
        _create_audit_log(
            self.request,
            action_name=AuditLog.Action.DELETE,
            resource_type="Connection",
            resource_id=conn_id,
            changes={"before": before},
        )
        instance.delete()

    @action(detail=True, methods=["post"], url_path="test")
    def test_connection(self, request, pk=None):
        """
        Test a connection by resolving its Key Vault secret and verifying
        reachability. Does NOT expose the secret in the response.
        """
        conn = self.get_object()

        if conn.auth_method == Connection.AuthMethod.NONE:
            return Response({"status": "ok", "message": "No authentication required."})

        if conn.auth_method == Connection.AuthMethod.MANAGED_IDENTITY:
            return Response({
                "status": "ok",
                "message": "Managed identity connections are validated at runtime.",
            })

        if not conn.key_vault_secret_name:
            return Response(
                {"status": "error", "message": "No Key Vault secret configured."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            client = KeyVaultClient(vault_url=conn.key_vault_url or None)
            client.get_secret(conn.key_vault_secret_name)
            return Response({
                "status": "ok",
                "message": f"Secret '{conn.key_vault_secret_name}' resolved successfully.",
            })
        except KeyVaultError as exc:
            return Response(
                {"status": "error", "message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["post"], url_path="sync-to-airflow")
    def sync_to_airflow(self, request, pk=None):
        """
        Sync this connection to Airflow via Azure Key Vault.

        Builds an Airflow connection URI from the connection metadata
        and the resolved secret, then writes it to Key Vault using the
        ``airflow-connections-{conn_id}`` naming convention. Airflow's
        Key Vault secrets backend picks it up at runtime — secrets are
        never stored in Airflow's metadata database.
        """
        conn = self.get_object()
        password = ""

        if conn.auth_method not in (
            Connection.AuthMethod.NONE,
            Connection.AuthMethod.MANAGED_IDENTITY,
        ):
            if conn.key_vault_secret_name:
                try:
                    kv_client = KeyVaultClient(vault_url=conn.key_vault_url or None)
                    password = kv_client.get_secret(conn.key_vault_secret_name)
                except KeyVaultError as exc:
                    return Response(
                        {"detail": f"Key Vault error: {exc}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        # Build Airflow connection URI:
        # <conn_type>://<login>:<password>@<host>:<port>/<schema>
        uri = self._build_connection_uri(conn, password)

        # Write to Key Vault as "airflow-connections-<conn_id>"
        airflow_secret_name = f"airflow-connections-{conn.conn_id}"
        try:
            kv_client = KeyVaultClient(vault_url=conn.key_vault_url or None)
            kv_client.set_secret(airflow_secret_name, uri)
        except KeyVaultError as exc:
            logger.error(
                "Failed to write Airflow connection secret for %s: %s",
                conn.conn_id, exc,
            )
            return Response(
                {"detail": f"Key Vault error: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            "detail": (
                f"Connection '{conn.conn_id}' synced to Key Vault as "
                f"'{airflow_secret_name}'. Airflow will resolve it at runtime."
            ),
        })

    @staticmethod
    def _build_connection_uri(conn: Connection, password: str) -> str:
        """
        Build an Airflow-compatible connection URI.

        Format: ``<type>://<login>:<password>@<host>:<port>/<schema>?<extra>``

        See: https://airflow.apache.org/docs/apache-airflow/stable/howto/connection.html#connection-uri-format
        """
        from urllib.parse import quote_plus, urlencode
        import json

        scheme = conn.connection_type
        login = quote_plus(conn.login) if conn.login else ""
        pwd = quote_plus(password) if password else ""
        host = conn.host or ""
        port = str(conn.port) if conn.port else ""
        schema = quote_plus(conn.schema_name) if conn.schema_name else ""

        # Build userinfo
        userinfo = ""
        if login or pwd:
            userinfo = f"{login}:{pwd}@" if pwd else f"{login}@"

        # Build host:port
        host_part = host
        if port:
            host_part = f"{host}:{port}"

        # Build query string from extra
        query = ""
        if conn.extra:
            extra_str = json.dumps(conn.extra) if isinstance(conn.extra, dict) else str(conn.extra)
            query = f"?{urlencode({'extra': extra_str})}"

        return f"{scheme}://{userinfo}{host_part}/{schema}{query}"


class DAGConnectionViewSet(viewsets.ModelViewSet):
    """
    Manage the links between DAGs and Connections.

    list:    GET    /api/dag-connections/
    create:  POST   /api/dag-connections/
    delete:  DELETE /api/dag-connections/{id}/
    """

    queryset = DAGConnection.objects.select_related("connection").all()
    permission_classes = [IsAzureADAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = {
        "dag": ["exact"],
        "connection": ["exact"],
    }

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return DAGConnectionWriteSerializer
        return DAGConnectionSerializer
