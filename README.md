# DAG Manager - Backend

Django REST Framework API for managing Apache Airflow DAG definitions, scheduling, monitoring, and audit logging. Authenticates requests via Azure AD JWT tokens and communicates with an on-prem Airflow instance using Azure User Managed Identities (via Azure ARC).

## Features

- **DAG Management** - Full CRUD for Airflow DAG definitions including Python script content, cron-based scheduling, retry/timeout configuration, tags, and arbitrary JSON configuration
- **Connection Management** - Hybrid connection system where metadata lives in the app database and secrets are stored in Azure Key Vault. Connections are synced as Key Vault secrets that Airflow resolves at runtime — secrets never touch Airflow's database
- **DAG Run Monitoring** - Track execution runs with state (queued, running, success, failed, skipped), timing, and per-run log entries
- **Airflow Integration** - Trigger, pause, unpause, and sync DAGs and connections to an on-prem Apache Airflow server via its REST API
- **Audit Logging** - Immutable audit trail for every CREATE, UPDATE, DELETE, TRIGGER, PAUSE, and UNPAUSE action with before/after snapshots, user identity, IP address, and user agent
- **Azure AD Authentication** - JWT bearer token validation against Azure AD JWKS endpoints with automatic key rotation and caching
- **Azure Managed Identity** - Airflow client authenticates using a user-assigned managed identity provided through Azure ARC
- **Filtering and Search** - Filter DAGs by active status, owner, and tags; search by name, DAG ID, and description; filter runs by state and date range; filter audit logs by user, action, resource type, and date range
- **Pagination and Ordering** - Configurable page sizes with cursor-based ordering on all list endpoints

## Tech Stack

| Component | Technology |
|---|---|
| Framework | Django 4.2 + Django REST Framework 3.14+ |
| Authentication | Azure AD JWT (PyJWT + cryptography) |
| Airflow Auth | Azure Managed Identity (azure-identity) |
| Secret Storage | Azure Key Vault (azure-keyvault-secrets) |
| Database | SQLite (dev) / MySQL (prod) |
| Filtering | django-filter |
| CORS | django-cors-headers |
| Testing | pytest + pytest-django + factory-boy |

## Project Structure

```
backend/
├── dag_manager/          # Django project settings, root URLs, WSGI/ASGI
├── dags/                 # DAG models, views, serializers, permissions
│   ├── models.py         # DAG, DAGRun, DAGRunLog
│   ├── views.py          # DAGViewSet (CRUD + trigger/pause/unpause/sync/runs)
│   ├── serializers.py    # DAGSerializer, DAGListSerializer, DAGRunSerializer, etc.
│   ├── permissions.py    # IsAzureADAuthenticated, IsOwnerOrReadOnly
│   └── urls.py
├── audit/                # Audit log model, read-only API, request metadata middleware
│   ├── models.py         # AuditLog
│   ├── views.py          # AuditLogViewSet (read-only)
│   └── middleware.py     # Captures IP, user agent into thread-local storage
├── authentication/       # Azure AD token validation
│   ├── backend.py        # AzureADAuthentication (DRF auth class), JWKSKeyCache, AzureADUser
│   ├── middleware.py      # AzureADTokenMiddleware
│   └── views.py          # /api/auth/me/, /api/auth/health/
├── connections/          # Connection management (metadata + Key Vault secrets)
│   ├── models.py         # Connection, DAGConnection
│   ├── views.py          # ConnectionViewSet (CRUD + test + sync-to-airflow)
│   ├── serializers.py    # ConnectionSerializer, DAGConnectionSerializer, etc.
│   ├── keyvault.py       # KeyVaultClient (Azure Managed Identity + caching)
│   └── urls.py
├── airflow_client/       # Airflow REST API client
│   └── client.py         # AirflowClient with Managed Identity auth
├── tests/                # Unit and integration tests (116 tests)
├── manage.py
├── requirements.txt
├── pytest.ini
└── setup.cfg
```

## Prerequisites

- Python 3.10+
- pip

## Installation

1. **Clone the repository** and navigate to the backend directory:

   ```bash
   cd backend
   ```

2. **Create a virtual environment** (recommended):

   ```bash
   python -m venv venv
   source venv/bin/activate    # Linux/macOS
   venv\Scripts\activate       # Windows
   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and fill in your values (see [Configuration](#configuration) below).

5. **Run database migrations:**

   ```bash
   python manage.py migrate
   ```

6. **Create a superuser** (optional, for Django admin):

   ```bash
   python manage.py createsuperuser
   ```

## Running the Server

**Development:**

```bash
python manage.py runserver
```

The API will be available at `http://localhost:8000/api/`.

**Production (gunicorn):**

```bash
gunicorn dag_manager.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

## Configuration

All configuration is done via environment variables. Copy `.env.example` to `.env` and set the following:

### Required

| Variable | Description |
|---|---|
| `AZURE_AD_TENANT_ID` | Your Azure AD tenant ID |
| `AZURE_AD_CLIENT_ID` | The app registration client ID for this backend |
| `AZURE_AD_AUDIENCE` | Token audience (usually `api://<client-id>`) |
| `AIRFLOW_BASE_URL` | URL of your on-prem Airflow server (e.g. `http://airflow.internal:8080`) |
| `AZURE_MANAGED_IDENTITY_CLIENT_ID` | Client ID of the user-assigned managed identity for Airflow auth |
| `AZURE_KEY_VAULT_URL` | Azure Key Vault URL (e.g. `https://my-vault.vault.azure.net`) |

### Optional

| Variable | Default | Description |
|---|---|---|
| `DJANGO_SECRET_KEY` | insecure dev key | Django secret key (change in production) |
| `DJANGO_DEBUG` | `True` | Enable debug mode |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed hosts |
| `DB_ENGINE` | `django.db.backends.sqlite3` | Database engine |
| `DB_NAME` | `db.sqlite3` | Database name |
| `DB_USER` | `` | Database user |
| `DB_PASSWORD` | `` | Database password |
| `DB_HOST` | `` | Database host |
| `DB_PORT` | `` | Database port |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated CORS origins |

### Development Mode

When `AZURE_AD_TENANT_ID` is not set, the authentication middleware skips token validation, allowing unauthenticated access for local development. Use `force_authenticate` in tests or disable the auth classes for rapid iteration.

## API Endpoints

### DAGs

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/dags/` | List DAGs (paginated, filterable, searchable) |
| POST | `/api/dags/` | Create a new DAG |
| GET | `/api/dags/{id}/` | Retrieve DAG details |
| PUT | `/api/dags/{id}/` | Update a DAG |
| PATCH | `/api/dags/{id}/` | Partially update a DAG |
| DELETE | `/api/dags/{id}/` | Delete a DAG |
| POST | `/api/dags/{id}/trigger/` | Trigger a DAG run (optional `conf` body) |
| POST | `/api/dags/{id}/pause/` | Pause the DAG |
| POST | `/api/dags/{id}/unpause/` | Unpause the DAG |
| POST | `/api/dags/{id}/sync/` | Sync DAG definition to Airflow |
| GET | `/api/dags/{id}/runs/` | List runs for a specific DAG |

### Connections

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/connections/` | List connections (filterable by type, auth method, status) |
| POST | `/api/connections/` | Create a new connection |
| GET | `/api/connections/{id}/` | Retrieve connection details |
| PUT | `/api/connections/{id}/` | Update a connection |
| DELETE | `/api/connections/{id}/` | Delete a connection |
| POST | `/api/connections/{id}/test/` | Test connection (resolves Key Vault secret) |
| POST | `/api/connections/{id}/sync-to-airflow/` | Write connection URI to Key Vault for Airflow |

### DAG Connections

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/dag-connections/` | List DAG-connection links (filterable by dag, connection) |
| POST | `/api/dag-connections/` | Link a connection to a DAG (with optional alias) |
| DELETE | `/api/dag-connections/{id}/` | Remove a DAG-connection link |

### Runs

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/runs/` | List all DAG runs (filterable by state, date) |
| GET | `/api/runs/{id}/` | Retrieve run details |
| GET | `/api/runs/{id}/logs/` | Get log entries for a run |

### Audit

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/audit/` | List audit log entries (filterable) |
| GET | `/api/audit/{id}/` | Retrieve a single audit entry |

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/auth/me/` | Current user profile (from Azure AD token) |
| GET | `/api/auth/health/` | Health check (no auth required) |

## Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage report
python -m pytest tests/ --cov=. --cov-report=term-missing

# Run only unit tests (exclude integration)
python -m pytest tests/ -v -m "not integration"

# Run only integration tests
python -m pytest tests/ -v -m integration

# Run a specific test file
python -m pytest tests/test_views.py -v

# Run a specific test class
python -m pytest tests/test_views.py::TestDAGViewSetCRUD -v
```

### Test Structure

| File | Scope | Tests |
|---|---|---|
| `test_models.py` | DAG, DAGRun, DAGRunLog, AuditLog model behavior | 21 |
| `test_serializers.py` | Serializer field validation and output | 11 |
| `test_views.py` | DAGViewSet CRUD + actions, DAGRunViewSet | 26 |
| `test_audit_views.py` | AuditLogViewSet filtering, read-only enforcement | 8 |
| `test_auth.py` | Azure AD token validation, JWKS cache, auth views | 14 |
| `test_airflow_client.py` | Airflow REST client methods, error handling | 16 |
| `test_permissions.py` | IsAzureADAuthenticated, IsOwnerOrReadOnly | 8 |
| `test_integration.py` | Full CRUD flow, trigger flow, audit trail completeness | 4 |
| **Total** | | **116** |

## Connection Management

DAG Manager uses a hybrid approach for managing external service connections:

- **Metadata** (host, port, type, login) is stored in the app's database
- **Secrets** (passwords, API keys, connection strings) are stored in Azure Key Vault and referenced by secret name
- **Syncing** pushes the resolved connection (metadata + secret) to Airflow's connection store via its REST API

### Supported Connection Types

PostgreSQL, MySQL, SQL Server, Oracle, SQLite, HTTP/HTTPS, FTP/SFTP, SSH, AWS, Azure Blob Storage, Azure Data Lake, Azure Cosmos DB, Google Cloud, Redis, MongoDB, Elasticsearch, Kafka, SMTP, and Generic.

### Authentication Methods

| Method | Description |
|---|---|
| `none` | No authentication required |
| `user_password` | Username + password stored in Key Vault |
| `managed_identity` | Azure Managed Identity (no secret needed) |
| `key_vault_secret` | Full connection string stored in Key Vault |
| `api_key` | API key stored in Key Vault |
| `certificate` | Certificate stored in Key Vault |

### Using Connections in DAG Python Scripts

When you create a connection in DAG Manager and sync it to Airflow, the `conn_id` (e.g. `prod_postgres`) becomes available as a standard Airflow connection. Your DAG scripts reference it by ID — they never handle secrets directly.

**Using Airflow hooks (recommended):**

```python
from airflow.providers.postgres.hooks.postgres import PostgresHook

hook = PostgresHook(postgres_conn_id="prod_postgres")
df = hook.get_pandas_df("SELECT * FROM sales WHERE date = CURRENT_DATE")
```

**Using Airflow operators:**

```python
from airflow.providers.postgres.operators.postgres import PostgresOperator

query_task = PostgresOperator(
    task_id="extract_sales",
    postgres_conn_id="prod_postgres",
    sql="SELECT * FROM sales WHERE date = '{{ ds }}'",
)
```

**Using BaseHook for generic access:**

```python
from airflow.hooks.base import BaseHook

conn = BaseHook.get_connection("prod_postgres")
# conn.host, conn.port, conn.login, conn.password, conn.schema
```

**Common patterns by connection type:**

```python
# Microsoft SQL Server (MSSQL)
from airflow.providers.microsoft.mssql.hooks.mssql import MsSqlHook
hook = MsSqlHook(mssql_conn_id="prod_mssql")
df = hook.get_pandas_df("SELECT TOP 100 * FROM dbo.orders")

# MySQL
from airflow.providers.mysql.hooks.mysql import MySqlHook
hook = MySqlHook(mysql_conn_id="prod_mysql")
records = hook.get_records("SELECT * FROM users WHERE active = 1")

# HTTP/HTTPS REST API (scheme is determined by the connection type)
from airflow.providers.http.hooks.http import HttpHook
hook = HttpHook(http_conn_id="crm_api", method="GET")
response = hook.run("/api/v2/tickets")

# SMTP Email
from airflow.providers.smtp.hooks.smtp import SmtpHook
hook = SmtpHook(smtp_conn_id="smtp_reports")
hook.send_email_smtp(to="team@example.com", subject="Report", html_content=html)

# Azure Blob Storage
from airflow.providers.microsoft.azure.hooks.wasb import WasbHook
hook = WasbHook(wasb_conn_id="azure_blob_backups")
hook.load_string(data, container_name="db-backups", blob_name="backup.sql")

# SFTP
from airflow.providers.sftp.hooks.sftp import SFTPHook
hook = SFTPHook(ssh_conn_id="sftp_server")
hook.retrieve_file("/remote/path/file.csv", "/local/path/file.csv")

# Redis
from airflow.providers.redis.hooks.redis import RedisHook
hook = RedisHook(redis_conn_id="redis_cache")
hook.get_conn().set("key", "value")
```

The key concept: **`conn_id` is the bridge** between DAG Manager and your script. Define the connection once in the UI, sync it to Airflow, and reference it by ID in your code.

### How Connection Data Flows

```
Azure Key Vault               DAG Manager DB              Airflow Server
(secrets + connection URIs)   (metadata + refs)           (no secrets stored)
┌─────────────────────┐     ┌───────────────────┐     ┌──────────────────┐
│ prod-postgres-pwd   │◄────│ host, port, login │     │                  │
│ crm-api-key         │     │ key_vault_secret  │     │  At runtime,     │
│                     │     │ type, auth_method │     │  Airflow queries │
│ airflow-connections-│◄────│                   │     │  Key Vault for   │
│   prod_postgres     │  "Sync to Airflow"     │     │  connection URIs │
│ airflow-connections-│  builds URI from       │────►│  using its       │
│   crm_api           │  metadata + secret,    │     │  secrets backend │
│                     │  writes to Key Vault   │     │                  │
└─────────────────────┘     └───────────────────┘     └──────────────────┘
```

**Secrets never touch Airflow's database.** The architecture uses three components:

1. **Azure Key Vault** — stores both the raw secrets (passwords, API keys) and the Airflow connection URIs. When you click "Sync to Airflow", DAG Manager resolves the raw secret, builds a full connection URI, and writes it back to Key Vault as `airflow-connections-{conn_id}`.

2. **DAG Manager database** — stores connection metadata (host, port, type, login) and the Key Vault secret name. This is the source of truth you manage through the UI.

3. **Airflow server** — configured with the [Azure Key Vault secrets backend](https://airflow.apache.org/docs/apache-airflow-providers-microsoft-azure/stable/secrets-backends/azure-key-vault.html). At DAG runtime, when a hook or operator requests a connection, Airflow queries Key Vault for `airflow-connections-{conn_id}` and resolves the full URI on the fly. No secrets are stored in Airflow's metadata database.

**Secret rotation**: after rotating a secret in Key Vault, re-sync the connection from DAG Manager. This rebuilds the Airflow connection URI with the new secret and writes it to Key Vault. Airflow picks up the change immediately on the next DAG run — no Airflow restart needed.

### Airflow Key Vault Secrets Backend Configuration

To enable Airflow to read connections from Key Vault, add the following to your `airflow.cfg` (or set the equivalent environment variables):

```ini
[secrets]
backend = airflow.providers.microsoft.azure.secrets.key_vault.AzureKeyVaultBackend
backend_kwargs = {"connections_prefix": "airflow-connections", "vault_url": "https://your-vault.vault.azure.net"}
```

Or via environment variables:

```bash
AIRFLOW__SECRETS__BACKEND=airflow.providers.microsoft.azure.secrets.key_vault.AzureKeyVaultBackend
AIRFLOW__SECRETS__BACKEND_KWARGS='{"connections_prefix": "airflow-connections", "vault_url": "https://your-vault.vault.azure.net"}'
```

Airflow authenticates to Key Vault using the same managed identity configured via Azure ARC. Install the provider package on the Airflow server:

```bash
pip install apache-airflow-providers-microsoft-azure
```

## Azure ARC Integration

The Airflow client authenticates to the on-prem Airflow server using a user-assigned managed identity. This identity is provisioned on the Airflow server via Azure ARC, which extends Azure management capabilities to on-prem infrastructure.

The authentication flow:

1. Backend creates a `ManagedIdentityCredential` with the configured `AZURE_MANAGED_IDENTITY_CLIENT_ID`
2. For each Airflow API call, a token is requested scoped to the Airflow application
3. The token is passed as a Bearer token in the Authorization header
4. Airflow validates the token against Azure AD

This eliminates the need for static API keys or username/password credentials.
