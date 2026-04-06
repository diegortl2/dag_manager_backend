"""Unit tests for audit log views."""

import pytest
from rest_framework import status

from audit.models import AuditLog


@pytest.mark.django_db
class TestAuditLogViewSet:
    def test_list_audit_logs(self, authenticated_client, sample_audit_log):
        response = authenticated_client.get("/api/audit/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["action"] == "CREATE"

    def test_retrieve_audit_log(self, authenticated_client, sample_audit_log):
        response = authenticated_client.get(f"/api/audit/{sample_audit_log.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["user"] == "test@example.com"
        assert response.data["resource_type"] == "DAG"

    def test_filter_by_user(self, authenticated_client, sample_audit_log):
        response = authenticated_client.get("/api/audit/", {"user": "test@example.com"})
        assert response.data["count"] == 1

        response = authenticated_client.get("/api/audit/", {"user": "nobody@test.com"})
        assert response.data["count"] == 0

    def test_filter_by_action(self, authenticated_client, sample_audit_log):
        response = authenticated_client.get("/api/audit/", {"action": "CREATE"})
        assert response.data["count"] == 1

        response = authenticated_client.get("/api/audit/", {"action": "DELETE"})
        assert response.data["count"] == 0

    def test_filter_by_resource_type(self, authenticated_client, sample_audit_log):
        response = authenticated_client.get("/api/audit/", {"resource_type": "DAG"})
        assert response.data["count"] == 1

        response = authenticated_client.get("/api/audit/", {"resource_type": "DAGRun"})
        assert response.data["count"] == 0

    def test_audit_logs_are_read_only(self, authenticated_client):
        response = authenticated_client.post("/api/audit/", {}, format="json")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

        response = authenticated_client.put("/api/audit/some-id/", {}, format="json")
        assert response.status_code in (
            status.HTTP_405_METHOD_NOT_ALLOWED,
            status.HTTP_404_NOT_FOUND,
        )

        response = authenticated_client.delete("/api/audit/some-id/")
        assert response.status_code in (
            status.HTTP_405_METHOD_NOT_ALLOWED,
            status.HTTP_404_NOT_FOUND,
        )

    def test_unauthenticated_access_denied(self, api_client, sample_audit_log):
        response = api_client.get("/api/audit/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_ordering_by_timestamp(self, authenticated_client, azure_user, sample_dag):
        AuditLog.objects.create(
            user=azure_user.email, action="UPDATE",
            resource_type="DAG", resource_id=str(sample_dag.id),
        )
        AuditLog.objects.create(
            user=azure_user.email, action="DELETE",
            resource_type="DAG", resource_id=str(sample_dag.id),
        )
        response = authenticated_client.get("/api/audit/", {"ordering": "-timestamp"})
        results = response.data["results"]
        assert len(results) >= 2
        assert results[0]["timestamp"] >= results[1]["timestamp"]
