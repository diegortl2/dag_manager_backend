"""Unit tests for the Airflow REST API client."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from airflow_client.client import (
    AirflowClient,
    AirflowClientError,
    AirflowConnectionError,
    AirflowNotFoundError,
)


@pytest.fixture
def mock_credential():
    with patch("airflow_client.client.ManagedIdentityCredential") as MockCred:
        mock_cred = MagicMock()
        mock_cred.get_token.return_value = MagicMock(token="mock-mi-token")
        MockCred.return_value = mock_cred
        yield mock_cred


@pytest.fixture
def client(mock_credential):
    with patch("airflow_client.client.settings") as mock_settings:
        mock_settings.AIRFLOW_BASE_URL = "http://airflow.local:8080"
        mock_settings.AZURE_MANAGED_IDENTITY_CLIENT_ID = "mi-client-id-123"
        return AirflowClient(
            base_url="http://airflow.local:8080",
            managed_identity_client_id="mi-client-id-123",
        )


class TestAirflowClientURLs:
    def test_build_url(self, client):
        url = client._build_url("/dags")
        assert url == "http://airflow.local:8080/api/v1/dags"

    def test_build_url_strips_leading_slash(self, client):
        url = client._build_url("dags/my_dag")
        assert url == "http://airflow.local:8080/api/v1/dags/my_dag"


class TestAirflowClientMethods:
    @patch("airflow_client.client.requests.request")
    def test_list_dags(self, mock_request, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"dags": [], "total_entries": 0}
        mock_request.return_value = mock_response

        result = client.list_dags(limit=50, offset=10)
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args
        assert call_kwargs.kwargs["params"] == {"limit": 50, "offset": 10}
        assert "/dags" in call_kwargs.kwargs["url"]

    @patch("airflow_client.client.requests.request")
    def test_get_dag(self, mock_request, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"dag_id": "my_dag"}
        mock_request.return_value = mock_response

        result = client.get_dag("my_dag")
        assert result["dag_id"] == "my_dag"
        call_url = mock_request.call_args.kwargs["url"]
        assert "/dags/my_dag" in call_url

    @patch("airflow_client.client.requests.request")
    def test_trigger_dag(self, mock_request, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"dag_run_id": "run_1"}
        mock_request.return_value = mock_response

        result = client.trigger_dag("my_dag", conf={"key": "val"})
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["json"] == {"conf": {"key": "val"}}
        assert "/dags/my_dag/dagRuns" in call_kwargs["url"]

    @patch("airflow_client.client.requests.request")
    def test_trigger_dag_without_conf(self, mock_request, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"dag_run_id": "run_1"}
        mock_request.return_value = mock_response

        client.trigger_dag("my_dag")
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["json"] == {}

    @patch("airflow_client.client.requests.request")
    def test_pause_dag(self, mock_request, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"is_paused": True}
        mock_request.return_value = mock_response

        client.pause_dag("my_dag")
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["json"] == {"is_paused": True}
        assert call_kwargs["method"] == "PATCH"

    @patch("airflow_client.client.requests.request")
    def test_unpause_dag(self, mock_request, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"is_paused": False}
        mock_request.return_value = mock_response

        client.unpause_dag("my_dag")
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["json"] == {"is_paused": False}

    @patch("airflow_client.client.requests.request")
    def test_sync_dag(self, mock_request, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "synced"}
        mock_request.return_value = mock_response

        dag_data = {"dag_id": "my_dag", "python_script": "print('hi')"}
        result = client.sync_dag(dag_data)
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["json"] == dag_data
        assert "/dags/sync" in call_kwargs["url"]

    @patch("airflow_client.client.requests.request")
    def test_get_dag_runs(self, mock_request, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"dag_runs": []}
        mock_request.return_value = mock_response

        client.get_dag_runs("my_dag", limit=10, offset=5)
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["params"]["limit"] == 10
        assert call_kwargs["params"]["offset"] == 5

    @patch("airflow_client.client.requests.request")
    def test_get_dag_run(self, mock_request, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"dag_run_id": "run_1"}
        mock_request.return_value = mock_response

        result = client.get_dag_run("my_dag", "run_1")
        call_url = mock_request.call_args.kwargs["url"]
        assert "/dags/my_dag/dagRuns/run_1" in call_url


class TestAirflowClientErrorHandling:
    @patch("airflow_client.client.requests.request")
    def test_404_raises_not_found(self, mock_request, client):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "Not found"}
        mock_request.return_value = mock_response

        with pytest.raises(AirflowNotFoundError):
            client.get_dag("nonexistent_dag")

    @patch("airflow_client.client.requests.request")
    def test_500_raises_client_error(self, mock_request, client):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Internal error"}
        mock_request.return_value = mock_response

        with pytest.raises(AirflowClientError) as exc_info:
            client.get_dag("my_dag")
        assert exc_info.value.status_code == 500

    @patch("airflow_client.client.requests.request")
    def test_connection_error(self, mock_request, client):
        mock_request.side_effect = requests.ConnectionError("Connection refused")

        with pytest.raises(AirflowConnectionError, match="Unable to connect"):
            client.get_dag("my_dag")

    @patch("airflow_client.client.requests.request")
    def test_timeout_error(self, mock_request, client):
        mock_request.side_effect = requests.Timeout("Timed out")

        with pytest.raises(AirflowConnectionError, match="timed out"):
            client.get_dag("my_dag")

    @patch("airflow_client.client.requests.request")
    def test_204_returns_none(self, mock_request, client):
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_request.return_value = mock_response

        result = client._request("DELETE", "/some-resource")
        assert result is None

    @patch("airflow_client.client.requests.request")
    def test_headers_include_bearer_token(self, mock_request, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_request.return_value = mock_response

        client.list_dags()
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["headers"]["Authorization"] == "Bearer mock-mi-token"
