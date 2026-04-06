"""Unit and integration tests for DAG views."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status

from audit.models import AuditLog
from dags.models import DAG, DAGRun


@pytest.mark.django_db
class TestDAGViewSetList:
    def test_list_dags(self, authenticated_client, sample_dag):
        response = authenticated_client.get("/api/dags/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["dag_id"] == "etl_daily_sales"

    def test_list_uses_list_serializer(self, authenticated_client, sample_dag):
        response = authenticated_client.get("/api/dags/")
        result = response.data["results"][0]
        assert "python_script" not in result
        assert "dag_id" in result

    def test_filter_by_is_active(self, authenticated_client, sample_dag, inactive_dag):
        response = authenticated_client.get("/api/dags/", {"is_active": "true"})
        assert response.data["count"] == 1
        assert response.data["results"][0]["is_active"] is True

        response = authenticated_client.get("/api/dags/", {"is_active": "false"})
        assert response.data["count"] == 1
        assert response.data["results"][0]["is_active"] is False

    def test_search_by_name(self, authenticated_client, sample_dag, inactive_dag):
        response = authenticated_client.get("/api/dags/", {"search": "Daily Sales"})
        assert response.data["count"] == 1
        assert response.data["results"][0]["dag_id"] == "etl_daily_sales"

    def test_search_by_dag_id(self, authenticated_client, sample_dag):
        response = authenticated_client.get("/api/dags/", {"search": "etl_daily"})
        assert response.data["count"] == 1

    def test_unauthenticated_returns_forbidden(self, api_client, sample_dag):
        response = api_client.get("/api/dags/")
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


@pytest.mark.django_db
class TestDAGViewSetCRUD:
    def test_create_dag(self, authenticated_client):
        data = {
            "dag_id": "new_pipeline",
            "name": "New Pipeline",
            "python_script": "print('hello')",
            "schedule_interval": "@hourly",
            "is_active": False,
            "max_retries": 2,
            "retry_delay_seconds": 60,
            "timeout_seconds": 1800,
            "tags": ["new"],
            "configuration": {},
            "owner": "test@example.com",
            "description": "Brand new pipeline",
        }
        response = authenticated_client.post("/api/dags/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["dag_id"] == "new_pipeline"
        assert response.data["created_by"] == "test@example.com"

    def test_create_dag_creates_audit_log(self, authenticated_client):
        data = {
            "dag_id": "audited_dag",
            "name": "Audited",
            "python_script": "pass",
            "schedule_interval": "",
            "owner": "test@example.com",
        }
        authenticated_client.post("/api/dags/", data, format="json")
        audit = AuditLog.objects.filter(action="CREATE", resource_type="DAG").first()
        assert audit is not None
        assert audit.user == "test@example.com"
        assert "after" in audit.changes

    def test_retrieve_dag(self, authenticated_client, sample_dag):
        response = authenticated_client.get(f"/api/dags/{sample_dag.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["dag_id"] == "etl_daily_sales"
        assert "python_script" in response.data

    def test_update_dag(self, authenticated_client, sample_dag):
        data = {
            "dag_id": sample_dag.dag_id,
            "name": "Updated Name",
            "python_script": sample_dag.python_script,
            "owner": sample_dag.owner,
        }
        response = authenticated_client.put(
            f"/api/dags/{sample_dag.id}/", data, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Updated Name"
        assert response.data["updated_by"] == "test@example.com"

    def test_update_creates_audit_log(self, authenticated_client, sample_dag):
        data = {
            "dag_id": sample_dag.dag_id,
            "name": "Renamed DAG",
            "python_script": sample_dag.python_script,
            "owner": sample_dag.owner,
        }
        authenticated_client.put(f"/api/dags/{sample_dag.id}/", data, format="json")
        audit = AuditLog.objects.filter(action="UPDATE", resource_type="DAG").first()
        assert audit is not None
        assert "before" in audit.changes
        assert "after" in audit.changes

    def test_delete_dag(self, authenticated_client, sample_dag):
        response = authenticated_client.delete(f"/api/dags/{sample_dag.id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not DAG.objects.filter(id=sample_dag.id).exists()

    def test_delete_creates_audit_log(self, authenticated_client, sample_dag):
        dag_id = str(sample_dag.id)
        authenticated_client.delete(f"/api/dags/{sample_dag.id}/")
        audit = AuditLog.objects.filter(action="DELETE", resource_type="DAG").first()
        assert audit is not None
        assert audit.resource_id == dag_id
        assert "before" in audit.changes


@pytest.mark.django_db
class TestDAGViewSetActions:
    @patch("dags.views.AirflowClient")
    def test_trigger_action(self, MockClient, authenticated_client, sample_dag):
        mock_instance = MagicMock()
        mock_instance.trigger_dag.return_value = {
            "dag_run_id": "manual__2024-02-01T00:00:00",
            "execution_date": "2024-02-01T00:00:00+00:00",
        }
        MockClient.return_value = mock_instance

        response = authenticated_client.post(
            f"/api/dags/{sample_dag.id}/trigger/",
            {"conf": {"key": "val"}},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert DAGRun.objects.filter(dag=sample_dag).exists()
        mock_instance.trigger_dag.assert_called_once_with(
            sample_dag.dag_id, conf={"key": "val"}
        )

    @patch("dags.views.AirflowClient")
    def test_trigger_creates_audit_log(self, MockClient, authenticated_client, sample_dag):
        mock_instance = MagicMock()
        mock_instance.trigger_dag.return_value = {
            "dag_run_id": "run_1",
            "execution_date": "2024-02-01T00:00:00+00:00",
        }
        MockClient.return_value = mock_instance

        authenticated_client.post(
            f"/api/dags/{sample_dag.id}/trigger/", {}, format="json"
        )
        audit = AuditLog.objects.filter(action="TRIGGER").first()
        assert audit is not None
        assert audit.resource_type == "DAGRun"

    @patch("dags.views.AirflowClient")
    def test_pause_action(self, MockClient, authenticated_client, sample_dag):
        mock_instance = MagicMock()
        mock_instance.pause_dag.return_value = {}
        MockClient.return_value = mock_instance

        response = authenticated_client.post(f"/api/dags/{sample_dag.id}/pause/")
        assert response.status_code == status.HTTP_200_OK
        sample_dag.refresh_from_db()
        assert sample_dag.is_active is False
        mock_instance.pause_dag.assert_called_once_with(sample_dag.dag_id)

    @patch("dags.views.AirflowClient")
    def test_pause_creates_audit_log(self, MockClient, authenticated_client, sample_dag):
        MockClient.return_value = MagicMock()
        authenticated_client.post(f"/api/dags/{sample_dag.id}/pause/")
        audit = AuditLog.objects.filter(action="PAUSE").first()
        assert audit is not None

    @patch("dags.views.AirflowClient")
    def test_unpause_action(self, MockClient, authenticated_client, inactive_dag):
        mock_instance = MagicMock()
        mock_instance.unpause_dag.return_value = {}
        MockClient.return_value = mock_instance

        response = authenticated_client.post(f"/api/dags/{inactive_dag.id}/unpause/")
        assert response.status_code == status.HTTP_200_OK
        inactive_dag.refresh_from_db()
        assert inactive_dag.is_active is True

    @patch("dags.views.AirflowClient")
    def test_unpause_creates_audit_log(self, MockClient, authenticated_client, inactive_dag):
        MockClient.return_value = MagicMock()
        authenticated_client.post(f"/api/dags/{inactive_dag.id}/unpause/")
        audit = AuditLog.objects.filter(action="UNPAUSE").first()
        assert audit is not None

    @patch("dags.views.AirflowClient")
    def test_sync_action(self, MockClient, authenticated_client, sample_dag):
        mock_instance = MagicMock()
        mock_instance.sync_dag.return_value = {"status": "synced"}
        MockClient.return_value = mock_instance

        response = authenticated_client.post(f"/api/dags/{sample_dag.id}/sync/")
        assert response.status_code == status.HTTP_200_OK
        assert "synced" in response.data["detail"].lower()

    def test_runs_action(self, authenticated_client, sample_dag, sample_dag_run):
        response = authenticated_client.get(f"/api/dags/{sample_dag.id}/runs/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["run_id"] == sample_dag_run.run_id


@pytest.mark.django_db
class TestDAGRunViewSet:
    def test_list_runs(self, authenticated_client, sample_dag_run):
        response = authenticated_client.get("/api/runs/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1

    def test_retrieve_run(self, authenticated_client, sample_dag_run):
        response = authenticated_client.get(f"/api/runs/{sample_dag_run.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["state"] == "success"

    def test_runs_read_only(self, authenticated_client, sample_dag_run):
        response = authenticated_client.post("/api/runs/", {}, format="json")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_logs_action(self, authenticated_client, sample_dag_run, sample_dag_run_log):
        response = authenticated_client.get(f"/api/runs/{sample_dag_run.id}/logs/")
        assert response.status_code == status.HTTP_200_OK

    def test_filter_by_state(self, authenticated_client, sample_dag_run):
        response = authenticated_client.get("/api/runs/", {"state": "success"})
        assert response.data["count"] == 1

        response = authenticated_client.get("/api/runs/", {"state": "failed"})
        assert response.data["count"] == 0
