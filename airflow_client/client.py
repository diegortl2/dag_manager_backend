"""
Apache Airflow REST API client.

Authenticates to the on-prem Airflow server using an Azure Managed Identity
token obtained via ``azure-identity`` (user-assigned managed identity
provided through Azure ARC).
"""

import logging
from typing import Any, Optional

import requests
from azure.identity import ManagedIdentityCredential
from django.conf import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class AirflowClientError(Exception):
    """Generic Airflow API error."""

    def __init__(self, message: str, status_code: Optional[int] = None, detail: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class AirflowConnectionError(AirflowClientError):
    """Raised when the Airflow server cannot be reached."""


class AirflowNotFoundError(AirflowClientError):
    """Raised when the requested resource is not found (HTTP 404)."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class AirflowClient:
    """
    Client for the Apache Airflow Stable REST API (``/api/v1``).

    Uses Azure Managed Identity to obtain bearer tokens for authentication.
    The managed identity is a *user-assigned* identity whose ``client_id`` is
    configured via the ``AZURE_MANAGED_IDENTITY_CLIENT_ID`` setting.
    """

    API_PREFIX = "/api/v1"
    REQUEST_TIMEOUT = 30  # seconds

    def __init__(
        self,
        base_url: Optional[str] = None,
        managed_identity_client_id: Optional[str] = None,
    ):
        self._base_url = (base_url or settings.AIRFLOW_BASE_URL).rstrip("/")
        self._mi_client_id = (
            managed_identity_client_id or settings.AZURE_MANAGED_IDENTITY_CLIENT_ID
        )
        self._credential: Optional[ManagedIdentityCredential] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_credential(self) -> ManagedIdentityCredential:
        if self._credential is None:
            self._credential = ManagedIdentityCredential(
                client_id=self._mi_client_id,
            )
        return self._credential

    def _get_token(self) -> str:
        """Obtain an access token scoped to the Airflow resource."""
        credential = self._get_credential()
        # The scope is typically the application ID URI of the Airflow app
        # registration. We fall back to ``{base_url}/.default``.
        scope = f"{self._base_url}/.default"
        token = credential.get_token(scope)
        return token.token

    def _build_url(self, path: str) -> str:
        clean_path = path.lstrip("/")
        return f"{self._base_url}{self.API_PREFIX}/{clean_path}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> Any:
        url = self._build_url(path)
        logger.debug("%s %s", method.upper(), url)

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self._headers(),
                params=params,
                json=json_body,
                timeout=self.REQUEST_TIMEOUT,
            )
        except requests.ConnectionError as exc:
            raise AirflowConnectionError(
                f"Unable to connect to Airflow at {self._base_url}: {exc}"
            ) from exc
        except requests.Timeout as exc:
            raise AirflowConnectionError(
                f"Request to Airflow timed out after {self.REQUEST_TIMEOUT}s: {exc}"
            ) from exc
        except requests.RequestException as exc:
            raise AirflowClientError(
                f"Airflow request failed: {exc}"
            ) from exc

        return self._handle_response(response)

    @staticmethod
    def _handle_response(response: requests.Response) -> Any:
        if response.status_code == 404:
            detail = None
            try:
                detail = response.json()
            except ValueError:
                pass
            raise AirflowNotFoundError(
                "Resource not found.",
                status_code=404,
                detail=detail,
            )

        if response.status_code >= 400:
            detail = None
            try:
                detail = response.json()
            except ValueError:
                detail = response.text
            raise AirflowClientError(
                f"Airflow API error (HTTP {response.status_code}).",
                status_code=response.status_code,
                detail=detail,
            )

        if response.status_code == 204:
            return None

        try:
            return response.json()
        except ValueError:
            return response.text

    # ------------------------------------------------------------------
    # DAG operations
    # ------------------------------------------------------------------

    def list_dags(self, limit: int = 100, offset: int = 0) -> dict:
        """Return a paginated list of DAGs known to Airflow."""
        return self._request(
            "GET",
            "/dags",
            params={"limit": limit, "offset": offset},
        )

    def get_dag(self, dag_id: str) -> dict:
        """Retrieve details for a single DAG."""
        return self._request("GET", f"/dags/{dag_id}")

    def pause_dag(self, dag_id: str) -> dict:
        """Pause a DAG in Airflow."""
        return self._request(
            "PATCH",
            f"/dags/{dag_id}",
            json_body={"is_paused": True},
        )

    def unpause_dag(self, dag_id: str) -> dict:
        """Unpause a DAG in Airflow."""
        return self._request(
            "PATCH",
            f"/dags/{dag_id}",
            json_body={"is_paused": False},
        )

    def sync_dag(self, dag_data: dict) -> dict:
        """
        Push a DAG definition to Airflow.

        This sends the DAG metadata and Python script content to a custom
        sync endpoint. The Airflow server is expected to expose a plugin or
        API endpoint that accepts DAG definitions and writes them to its
        DAGs folder.

        ``dag_data`` should contain at least ``dag_id`` and ``python_script``.
        """
        return self._request(
            "POST",
            "/dags/sync",
            json_body=dag_data,
        )

    # ------------------------------------------------------------------
    # Connection operations
    # ------------------------------------------------------------------

    def sync_connection(self, connection_data: dict) -> dict:
        """
        Create or update an Airflow Connection.

        Uses the stable REST API: tries PATCH first (update), falls back
        to POST (create) if the connection doesn't exist yet.

        ``connection_data`` must contain at least ``connection_id`` and
        ``conn_type``.
        """
        conn_id = connection_data.get("connection_id", "")
        try:
            return self._request(
                "PATCH",
                f"/connections/{conn_id}",
                json_body=connection_data,
            )
        except AirflowNotFoundError:
            return self._request(
                "POST",
                "/connections",
                json_body=connection_data,
            )

    def delete_connection(self, connection_id: str) -> None:
        """Delete a connection from Airflow."""
        self._request("DELETE", f"/connections/{connection_id}")

    def get_connection(self, connection_id: str) -> dict:
        """Retrieve a single Airflow connection."""
        return self._request("GET", f"/connections/{connection_id}")

    # ------------------------------------------------------------------
    # DAG Run operations
    # ------------------------------------------------------------------

    def trigger_dag(self, dag_id: str, conf: Optional[dict] = None) -> dict:
        """Trigger a new DAG run."""
        body: dict[str, Any] = {}
        if conf:
            body["conf"] = conf
        return self._request(
            "POST",
            f"/dags/{dag_id}/dagRuns",
            json_body=body,
        )

    def get_dag_runs(
        self,
        dag_id: str,
        limit: int = 25,
        offset: int = 0,
    ) -> dict:
        """List DAG runs for a given DAG."""
        return self._request(
            "GET",
            f"/dags/{dag_id}/dagRuns",
            params={"limit": limit, "offset": offset, "order_by": "-execution_date"},
        )

    def get_dag_run(self, dag_id: str, run_id: str) -> dict:
        """Get a specific DAG run."""
        return self._request("GET", f"/dags/{dag_id}/dagRuns/{run_id}")

    def get_dag_run_logs(self, dag_id: str, run_id: str) -> dict:
        """
        Retrieve logs for a DAG run.

        Airflow's stable API exposes logs per task-instance rather than per
        DAG run. This method fetches the task instances for the run and then
        retrieves logs for each task.
        """
        # First, list task instances for this run.
        task_instances = self._request(
            "GET",
            f"/dags/{dag_id}/dagRuns/{run_id}/taskInstances",
        )

        logs: list[dict[str, Any]] = []
        for ti in task_instances.get("task_instances", []):
            task_id = ti.get("task_id")
            try_number = ti.get("try_number", 1)
            if not task_id:
                continue

            try:
                log_content = self._request(
                    "GET",
                    f"/dags/{dag_id}/dagRuns/{run_id}"
                    f"/taskInstances/{task_id}/logs/{try_number}",
                )
                logs.append(
                    {
                        "task_id": task_id,
                        "try_number": try_number,
                        "content": log_content,
                    }
                )
            except AirflowClientError as exc:
                logger.warning(
                    "Failed to fetch log for task %s try %s: %s",
                    task_id,
                    try_number,
                    exc,
                )
                logs.append(
                    {
                        "task_id": task_id,
                        "try_number": try_number,
                        "error": str(exc),
                    }
                )

        return {"dag_id": dag_id, "run_id": run_id, "logs": logs}
