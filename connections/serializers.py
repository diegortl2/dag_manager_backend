"""
DRF serializers for Connection management.
"""

from rest_framework import serializers

from .models import Connection, DAGConnection


class ConnectionSerializer(serializers.ModelSerializer):
    """Full serializer for Connection CRUD."""

    class Meta:
        model = Connection
        fields = [
            "id",
            "conn_id",
            "name",
            "description",
            "connection_type",
            "host",
            "port",
            "schema_name",
            "login",
            "auth_method",
            "key_vault_secret_name",
            "key_vault_url",
            "managed_identity_client_id",
            "extra",
            "is_active",
            "tags",
            "owner",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]


class ConnectionListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing connections."""

    class Meta:
        model = Connection
        fields = [
            "id",
            "conn_id",
            "name",
            "connection_type",
            "host",
            "port",
            "auth_method",
            "is_active",
            "tags",
            "owner",
            "updated_at",
        ]
        read_only_fields = fields


class DAGConnectionSerializer(serializers.ModelSerializer):
    """Serializer for the DAG-Connection link."""

    conn_id = serializers.CharField(source="connection.conn_id", read_only=True)
    connection_name = serializers.CharField(source="connection.name", read_only=True)
    connection_type = serializers.CharField(source="connection.connection_type", read_only=True)

    class Meta:
        model = DAGConnection
        fields = [
            "id",
            "dag",
            "connection",
            "conn_id",
            "connection_name",
            "connection_type",
            "alias",
        ]
        read_only_fields = ["id", "conn_id", "connection_name", "connection_type"]


class DAGConnectionWriteSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating DAG-Connection links."""

    class Meta:
        model = DAGConnection
        fields = ["id", "dag", "connection", "alias"]
        read_only_fields = ["id"]


class TestConnectionSerializer(serializers.Serializer):
    """Input for testing a connection."""

    connection_id = serializers.UUIDField(help_text="ID of the connection to test.")
