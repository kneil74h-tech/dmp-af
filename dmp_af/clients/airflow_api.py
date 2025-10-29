import requests
from requests.auth import HTTPBasicAuth
from typing import Dict, Optional, Any


class AirflowAPIError(Exception):
    """Base airflow API error."""
    pass


class AirflowAPIClient:
    """Client for interacting with Airflow REST API.

    This client provides a convenient interface to communicate with Airflow's
    REST API using Basic Authentication. It handles common API operations
    for DAGs, Tasks, Variables, and System Monitoring.

    Attributes:
        _base_url: Base URL of the Airflow instance.
        _auth: HTTPBasicAuth object for authentication.
    """
    def __init__(self, base_url: str, username: str, password: str) -> None:
        """Initialize the Airflow API client.

        Args:
            base_url: Base URL of the Airflow instance (without trailing slash).
            username: Username for Basic Authentication.
            password: Password for Basic Authentication.

        Raises:
            ValueError: If base_url is empty or invalid.
        """
        if not base_url:
            raise ValueError("Argument `base_url` cannot be empty.")

        self._base_url = base_url.rstrip("/")
        self._auth = HTTPBasicAuth(username, password)

    def _request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Execute HTTP request to Airflow API.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE).
            endpoint: API endpoint without leading slash.
            data: Optional JSON data for POST/PATCH requests.

        Returns:
            Dictionary containing API response.

        Raises:
            AirflowAPIError: If the request fails or returns non-200 status.
        """
        try:
            response = requests.request(
                method=method.upper(),
                url=f"{self._base_url}/api/v1/{endpoint}",
                auth=self._auth,
                json=data,
                timeout=60,
            )

            if response.status_code == 200:
                return response.json() if response.content else {}
            else:
                error_msg = f"API Error {response.status_code}: {response.text}."
                raise AirflowAPIError(error_msg)

        except requests.exceptions.RequestException as e:
            raise AirflowAPIError(f"Request failed: {str(e)}")

    def _get(self, endpoint: str) -> Dict[str, Any]:
        """Execute GET request.

        Args:
            endpoint: API endpoint.

        Returns:
            Dictionary with API response.
        """
        return self._request("GET", endpoint)

    def _post(self, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Execute POST request.

        Args:
            endpoint: API endpoint.
            data: JSON data to send.

        Returns:
            Dictionary with API response.
        """
        return self._request("POST", endpoint, data)

    def _patch(self, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Execute PATCH request.

        Args:
            endpoint: API endpoint.
            data: JSON data to send.

        Returns:
            Dictionary with API response.
        """
        return self._request("PATCH", endpoint, data)

    def _delete(self, endpoint: str) -> Dict[str, Any]:
        """Execute DELETE request.

        Args:
            endpoint: API endpoint.

        Returns:
            Dictionary with API response.
        """
        return self._request("DELETE", endpoint)

    def get_dags(self, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Retrieve list of all DAGs.

        Args:
            limit: Maximum number of DAGs to return.
            offset: Number of DAGs to skip.

        Returns:
            Dictionary containing DAGs list and metadata.
        """
        return self._get(f"dags?limit={limit}&offset={offset}")

    def get_task_instance(self, dag_id: str, dag_run_id: str, task_id: str) -> Dict[str, Any]:
        """Retrieve task instance info.

        Args:
            dag_id: The DAG ID for specific Task Instance.
            dag_run_id: The DAGRun ID for specific Task Instance.
            task_id: The Task ID.

        Returns:
            Dictionary containing info about specific task instance.
        """
        return self._get(f"/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}")
