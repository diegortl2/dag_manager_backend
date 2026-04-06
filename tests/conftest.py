"""
Shared pytest fixtures for the DAG Manager backend test suite.
"""

import uuid
from datetime import datetime, timezone

import pytest
from rest_framework.test import APIClient

from authentication.backend import AzureADUser
from audit.models import AuditLog
from dags.models import DAG, DAGRun, DAGRunLog


@pytest.fixture
def azure_user():
    """Return a realistic AzureADUser instance for testing."""
    return AzureADUser(
        oid="test-oid-123",
        email="test@example.com",
        name="Test User",
        roles=["admin"],
    )


@pytest.fixture
def other_azure_user():
    """Return a second AzureADUser for ownership / permission tests."""
    return AzureADUser(
        oid="other-oid-456",
        email="other@example.com",
        name="Other User",
        roles=["viewer"],
    )


@pytest.fixture
def api_client():
    """Return an unauthenticated DRF APIClient."""
    return APIClient()


@pytest.fixture
def authenticated_client(api_client, azure_user):
    """Return an APIClient force-authenticated with the azure_user fixture."""
    api_client.force_authenticate(user=azure_user)
    return api_client


@pytest.fixture
def other_authenticated_client(api_client, other_azure_user):
    """Return an APIClient force-authenticated with the other_azure_user."""
    client = APIClient()
    client.force_authenticate(user=other_azure_user)
    return client


@pytest.fixture
def sample_dag(azure_user):
    """Create and return a DAG instance with realistic data."""
    return DAG.objects.create(
        dag_id="etl_daily_sales",
        name="ETL Daily Sales",
        description="Daily ETL pipeline for sales data",
        python_script="from airflow import DAG\n# DAG definition here",
        schedule_interval="0 2 * * *",
        is_active=True,
        max_retries=3,
        retry_delay_seconds=300,
        timeout_seconds=3600,
        tags=["etl", "sales"],
        configuration={"source": "postgres", "destination": "bigquery"},
        owner=azure_user.email,
        created_by=azure_user.email,
        updated_by=azure_user.email,
    )


@pytest.fixture
def inactive_dag(azure_user):
    """Create and return an inactive DAG instance."""
    return DAG.objects.create(
        dag_id="etl_weekly_report",
        name="ETL Weekly Report",
        description="Weekly reporting pipeline",
        python_script="from airflow import DAG\n# weekly dag",
        schedule_interval="@weekly",
        is_active=False,
        owner=azure_user.email,
        created_by=azure_user.email,
    )


@pytest.fixture
def sample_dag_run(sample_dag):
    """Create and return a DAGRun for the sample_dag."""
    return DAGRun.objects.create(
        dag=sample_dag,
        run_id="manual__2024-01-15T10:00:00+00:00",
        state=DAGRun.State.SUCCESS,
        execution_date=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        start_date=datetime(2024, 1, 15, 10, 0, 5, tzinfo=timezone.utc),
        end_date=datetime(2024, 1, 15, 10, 15, 30, tzinfo=timezone.utc),
        external_trigger=True,
        conf={"param1": "value1"},
    )


@pytest.fixture
def sample_dag_run_log(sample_dag_run):
    """Create and return a DAGRunLog for the sample_dag_run."""
    return DAGRunLog.objects.create(
        dag_run=sample_dag_run,
        timestamp=datetime(2024, 1, 15, 10, 5, 0, tzinfo=timezone.utc),
        level=DAGRunLog.Level.INFO,
        message="Task etl_extract completed successfully.",
    )


@pytest.fixture
def sample_audit_log(azure_user, sample_dag):
    """Create and return an AuditLog entry."""
    return AuditLog.objects.create(
        user=azure_user.email,
        action=AuditLog.Action.CREATE,
        resource_type="DAG",
        resource_id=str(sample_dag.id),
        changes={"after": {"dag_id": sample_dag.dag_id, "name": sample_dag.name}},
        ip_address="127.0.0.1",
        user_agent="test-agent/1.0",
    )
