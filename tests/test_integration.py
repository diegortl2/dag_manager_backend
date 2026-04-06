"""Integration tests for full API workflows."""

from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status

from audit.models import AuditLog
from dags.models import DAG, DAGRun


@pytest.mark.django_db
@pytest.mark.integration
class TestFullCRUDFlow:
    def test_create_read_update_delete_with_audit(self, authenticated_client):
        # CREATE
        create_data = {
            "dag_id": "integration_test_dag",
            "name": "Integration Test DAG",
            "python_script": "print('integration test')",
            "schedule_interval": "0 6 * * *",
            "is_active": True,
            "max_retries": 2,
            "retry_delay_seconds": 120,
            "timeout_seconds": 7200,
            "tags": ["integration", "test"],
            "configuration": {"env": "test"},
            "owner": "test@example.com",
            "description": "Created for integration testing",
        }
        response = authenticated_client.post("/api/dags/", create_data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        dag_id = response.data["id"]

        # Verify it appears in list
        response = authenticated_client.get("/api/dags/")
        assert response.data["count"] == 1
        assert response.data["results"][0]["dag_id"] == "integration_test_dag"

        # READ
        response = authenticated_client.get(f"/api/dags/{dag_id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Integration Test DAG"
        assert response.data["python_script"] == "print('integration test')"

        # UPDATE
        update_data = {
            "dag_id": "integration_test_dag",
            "name": "Updated Integration DAG",
            "python_script": "print('updated')",
            "schedule_interval": "0 8 * * *",
            "owner": "test@example.com",
            "description": "Updated description",
        }
        response = authenticated_client.put(
            f"/api/dags/{dag_id}/", update_data, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Updated Integration DAG"

        # Verify audit logs exist for CREATE and UPDATE
        audit_logs = AuditLog.objects.filter(resource_id=dag_id).order_by("timestamp")
        assert audit_logs.count() == 2
        assert audit_logs[0].action == "CREATE"
        assert audit_logs[1].action == "UPDATE"
        assert "before" in audit_logs[1].changes
        assert "after" in audit_logs[1].changes

        # DELETE
        response = authenticated_client.delete(f"/api/dags/{dag_id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify it's gone
        response = authenticated_client.get(f"/api/dags/{dag_id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify DELETE audit log
        audit_logs = AuditLog.objects.filter(resource_id=dag_id).order_by("timestamp")
        assert audit_logs.count() == 3
        assert audit_logs[2].action == "DELETE"
        assert "before" in audit_logs[2].changes


@pytest.mark.django_db
@pytest.mark.integration
class TestTriggerFlow:
    @patch("dags.views.AirflowClient")
    def test_create_and_trigger_dag(self, MockClient, authenticated_client):
        mock_instance = MagicMock()
        mock_instance.trigger_dag.return_value = {
            "dag_run_id": "manual__2024-06-01T00:00:00",
            "execution_date": "2024-06-01T00:00:00+00:00",
        }
        MockClient.return_value = mock_instance

        # Create DAG
        create_data = {
            "dag_id": "trigger_test_dag",
            "name": "Trigger Test",
            "python_script": "print('trigger me')",
            "owner": "test@example.com",
        }
        response = authenticated_client.post("/api/dags/", create_data, format="json")
        dag_id = response.data["id"]

        # Trigger it
        response = authenticated_client.post(
            f"/api/dags/{dag_id}/trigger/",
            {"conf": {"run_mode": "full"}},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["state"] == "queued"
        assert response.data["external_trigger"] is True

        # Verify run was created
        assert DAGRun.objects.filter(dag_id=dag_id).count() == 1
        run = DAGRun.objects.get(dag_id=dag_id)
        assert run.conf == {"run_mode": "full"}

        # Verify audit trail
        trigger_audit = AuditLog.objects.filter(action="TRIGGER").first()
        assert trigger_audit is not None
        assert trigger_audit.resource_type == "DAGRun"
        assert trigger_audit.changes["dag_id"] == "trigger_test_dag"

        # Verify run appears in DAG runs endpoint
        response = authenticated_client.get(f"/api/dags/{dag_id}/runs/")
        assert response.data["count"] == 1

        # Also in global runs endpoint
        response = authenticated_client.get("/api/runs/")
        assert response.data["count"] == 1


@pytest.mark.django_db
@pytest.mark.integration
class TestPauseUnpauseFlow:
    @patch("dags.views.AirflowClient")
    def test_pause_and_unpause_dag(self, MockClient, authenticated_client):
        MockClient.return_value = MagicMock()

        # Create active DAG
        create_data = {
            "dag_id": "pause_test_dag",
            "name": "Pause Test",
            "python_script": "print('pause')",
            "is_active": True,
            "owner": "test@example.com",
        }
        response = authenticated_client.post("/api/dags/", create_data, format="json")
        dag_id = response.data["id"]

        # Pause it
        response = authenticated_client.post(f"/api/dags/{dag_id}/pause/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_active"] is False

        # Unpause it
        response = authenticated_client.post(f"/api/dags/{dag_id}/unpause/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_active"] is True

        # Verify audit trail has CREATE, PAUSE, UNPAUSE
        audits = AuditLog.objects.filter(resource_id=dag_id).order_by("timestamp")
        actions = [a.action for a in audits]
        assert "CREATE" in actions
        assert "PAUSE" in actions
        assert "UNPAUSE" in actions


@pytest.mark.django_db
@pytest.mark.integration
class TestAuditTrailCompleteness:
    @patch("dags.views.AirflowClient")
    def test_full_audit_trail(self, MockClient, authenticated_client):
        MockClient.return_value = MagicMock()
        MockClient.return_value.trigger_dag.return_value = {
            "dag_run_id": "run_audit",
            "execution_date": "2024-06-01T00:00:00+00:00",
        }

        # Create
        response = authenticated_client.post("/api/dags/", {
            "dag_id": "audit_trail_dag",
            "name": "Audit Trail Test",
            "python_script": "pass",
            "owner": "test@example.com",
        }, format="json")
        dag_id = response.data["id"]

        # Update
        authenticated_client.put(f"/api/dags/{dag_id}/", {
            "dag_id": "audit_trail_dag",
            "name": "Renamed",
            "python_script": "pass",
            "owner": "test@example.com",
        }, format="json")

        # Trigger
        authenticated_client.post(f"/api/dags/{dag_id}/trigger/", {}, format="json")

        # Pause
        authenticated_client.post(f"/api/dags/{dag_id}/pause/")

        # Delete
        authenticated_client.delete(f"/api/dags/{dag_id}/")

        # Verify all audit entries
        all_audits = AuditLog.objects.all().order_by("timestamp")
        actions = [a.action for a in all_audits]
        assert "CREATE" in actions
        assert "UPDATE" in actions
        assert "TRIGGER" in actions
        assert "PAUSE" in actions
        assert "DELETE" in actions

        # All entries should have user set
        for audit in all_audits:
            assert audit.user == "test@example.com"

        # Verify audit entries are queryable via API
        response = authenticated_client.get("/api/audit/")
        assert response.data["count"] == len(all_audits)
