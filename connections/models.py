"""
Connection models for managing external service credentials.

Stores connection metadata in the database. Actual secrets (passwords,
API keys, connection strings) are stored in Azure Key Vault and
referenced by vault secret name. At deploy time, connections are
synced to the Airflow Connections system.
"""

import uuid

from django.db import models


class Connection(models.Model):
    """
    An external service connection that DAGs can reference.

    Metadata (host, port, type) lives here. Secrets live in Azure Key Vault,
    referenced by ``key_vault_secret_name``. When syncing to Airflow,
    secrets are resolved from Key Vault and pushed as Airflow Connections.
    """

    class ConnectionType(models.TextChoices):
        POSTGRES = "postgres", "PostgreSQL"
        MYSQL = "mysql", "MySQL"
        MSSQL = "mssql", "Microsoft SQL Server"
        ORACLE = "oracle", "Oracle"
        SQLITE = "sqlite", "SQLite"
        HTTP = "http", "HTTP"
        HTTPS = "https", "HTTPS"
        FTP = "ftp", "FTP"
        SFTP = "sftp", "SFTP"
        SSH = "ssh", "SSH"
        AWS = "aws", "Amazon Web Services"
        AZURE_BLOB = "azure_blob", "Azure Blob Storage"
        AZURE_DATA_LAKE = "azure_data_lake", "Azure Data Lake"
        AZURE_COSMOS = "azure_cosmos", "Azure Cosmos DB"
        GOOGLE_CLOUD = "google_cloud", "Google Cloud"
        REDIS = "redis", "Redis"
        MONGO = "mongo", "MongoDB"
        ELASTICSEARCH = "elasticsearch", "Elasticsearch"
        KAFKA = "kafka", "Apache Kafka"
        SMTP = "smtp", "SMTP Email"
        GENERIC = "generic", "Generic"

    class AuthMethod(models.TextChoices):
        NONE = "none", "No Authentication"
        USER_PASSWORD = "user_password", "Username & Password (Key Vault)"
        MANAGED_IDENTITY = "managed_identity", "Azure Managed Identity"
        KEY_VAULT_SECRET = "key_vault_secret", "Connection String (Key Vault)"
        API_KEY = "api_key", "API Key (Key Vault)"
        CERTIFICATE = "certificate", "Certificate (Key Vault)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conn_id = models.CharField(
        max_length=250,
        unique=True,
        db_index=True,
        help_text="Unique connection identifier used in Airflow (e.g. 'prod_postgres').",
    )
    name = models.CharField(max_length=500, help_text="Human-readable display name.")
    description = models.TextField(blank=True, default="")
    connection_type = models.CharField(
        max_length=50,
        choices=ConnectionType.choices,
        default=ConnectionType.GENERIC,
        db_index=True,
    )
    host = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Hostname or IP address of the service.",
    )
    port = models.IntegerField(
        null=True,
        blank=True,
        help_text="Port number (e.g. 5432 for PostgreSQL).",
    )
    schema_name = models.CharField(
        max_length=250,
        blank=True,
        default="",
        help_text="Database name / schema / catalog.",
    )
    login = models.CharField(
        max_length=250,
        blank=True,
        default="",
        help_text="Username for authentication (non-secret).",
    )
    auth_method = models.CharField(
        max_length=50,
        choices=AuthMethod.choices,
        default=AuthMethod.USER_PASSWORD,
        help_text="How this connection authenticates to the remote service.",
    )
    key_vault_secret_name = models.CharField(
        max_length=250,
        blank=True,
        default="",
        help_text=(
            "Name of the secret in Azure Key Vault that holds the sensitive "
            "value (password, connection string, API key, or certificate)."
        ),
    )
    key_vault_url = models.URLField(
        max_length=500,
        blank=True,
        default="",
        help_text=(
            "Azure Key Vault URL. Defaults to the global AZURE_KEY_VAULT_URL setting."
        ),
    )
    managed_identity_client_id = models.CharField(
        max_length=250,
        blank=True,
        default="",
        help_text=(
            "Client ID of the user-assigned managed identity for this connection. "
            "Leave blank to use the default managed identity."
        ),
    )
    extra = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional connection parameters (non-secret key-value pairs).",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this connection is available for use.",
    )
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text="Tags for categorisation and filtering.",
    )
    owner = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.CharField(max_length=255, blank=True, default="")
    updated_by = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["name"]
        verbose_name = "Connection"
        verbose_name_plural = "Connections"

    def __str__(self) -> str:
        return f"{self.conn_id} ({self.name})"


class DAGConnection(models.Model):
    """
    Many-to-many link between a DAG and the connections it uses.

    Stores an optional ``alias`` so the same connection can be referenced
    by different logical names in different DAGs (e.g. 'source_db', 'target_db').
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dag = models.ForeignKey(
        "dags.DAG",
        on_delete=models.CASCADE,
        related_name="dag_connections",
    )
    connection = models.ForeignKey(
        Connection,
        on_delete=models.CASCADE,
        related_name="dag_connections",
    )
    alias = models.CharField(
        max_length=250,
        blank=True,
        default="",
        help_text=(
            "Optional alias for this connection within the DAG "
            "(e.g. 'source_db', 'output_api')."
        ),
    )

    class Meta:
        unique_together = [("dag", "connection")]
        ordering = ["alias", "connection__conn_id"]
        verbose_name = "DAG Connection"
        verbose_name_plural = "DAG Connections"

    def __str__(self) -> str:
        alias_part = f" as '{self.alias}'" if self.alias else ""
        return f"{self.dag.dag_id} → {self.connection.conn_id}{alias_part}"
