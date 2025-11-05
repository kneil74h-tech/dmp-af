"""Sensor for monitoring external Airflow tasks."""
from typing import TYPE_CHECKING, List, Dict, TypedDict

import pendulum
from airflow.hooks.base import BaseHook
from airflow.sensors.base import BaseSensorOperator

if TYPE_CHECKING:
    from airflow.utils.context import Context

from dmp_af.clients.airflow_api import AirflowAPIClient


class ExternalTaskConfig(TypedDict):
    """Configuration for an external task to monitor.

    Attributes:
        external_airflow_host: URL of the external Airflow instance.
        external_dag_id: DAG ID in the external Airflow instance.
        external_task_id: Task ID in the external Airflow instance.
        timedelta_min: Time delta in minutes for task execution time adjustment.
        api_connection_id: Airflow connection ID for API authentication.
    """
    external_airflow_host: str
    external_dag_id: str
    external_task_id: str
    timedelta_min: int
    api_connection_id: str


class ExternalAirflowTaskSensor(BaseSensorOperator):
    """Sensor that monitors completion of tasks in external Airflow instances.

    This sensor checks the status of tasks running in external Airflow environments
    and returns True when all monitored tasks have completed successfully.

    Args:
        task_id: Unique task identifier for the sensor.
        external_tasks: List of external task configurations to monitor.
        *args: Variable length argument list.
        **kwargs: Arbitrary keyword arguments.

    Attributes:
        _external_tasks: List of external task configurations.
        _api_clients: Dictionary mapping hosts to API client instances.
    """

    def __init__(self, task_id: str, external_tasks: List[ExternalTaskConfig], *args, **kwargs) -> None:
        """Initialize the ExternalAirflowTaskSensor.

        Args:
            task_id: Unique task identifier for the sensor.
            external_tasks: List of external task configurations to monitor.
            *args: Variable length argument list.
            **kwargs: Arbitrary keyword arguments.
        """
        super().__init__(task_id=task_id, *args, **kwargs)
        self._external_tasks = external_tasks
        self._api_clients = self._build_api_clients()

    def _build_api_clients(self) -> Dict[str, AirflowAPIClient]:
        """Build API clients for all unique external Airflow hosts.

        Returns:
            Dictionary mapping host URLs to AirflowAPIClient instances.
        """
        processed_hosts = {}

        for task_config in self._external_tasks:
            host = task_config["external_airflow_host"]
            if host not in processed_hosts:
                api_hook = BaseHook.get_connection(task_config["api_connection_id"])
                processed_hosts[host] = AirflowAPIClient(
                    base_url=host,
                    username=api_hook.login,
                    password=api_hook.password,
                )

        return processed_hosts

    def poke(self, context: 'Context') -> bool:
        """Check if all external tasks have completed successfully.

        Args:
            context: Airflow task context containing execution information.

        Returns:
            True if all external tasks are successful, False otherwise.
        """
        execution_ts = pendulum.parse(context["ts"])
        ready_tasks = []
        not_ready_tasks = []

        for task_config in self._external_tasks:
            task_ready = self._check_task_status(task_config, execution_ts)
            task_identifier = self._get_task_identifier(task_config)

            if task_ready:
                ready_tasks.append(task_identifier)
            else:
                not_ready_tasks.append(task_identifier)

        return self._handle_poke_result(ready_tasks, not_ready_tasks)

    def _check_task_status(self, task_config: ExternalTaskConfig, execution_ts: pendulum.DateTime) -> bool:
        """Check the status of a specific external task.

        Args:
            task_config: Configuration of the task to check.
            execution_ts: Execution timestamp from Airflow context.

        Returns:
            True if the task is successful, False otherwise.
        """
        adjusted_ts = execution_ts.add(minutes=task_config["timedelta_min"])

        task_instance = self._api_clients[task_config["external_airflow_host"]].get_task_instance(
            task_id=task_config["external_task_id"],
            dag_id=task_config["external_dag_id"],
            dag_run_id=f"scheduled__{adjusted_ts.to_iso8601_string()}",
        )

        return task_instance.get("state") == "success"

    @staticmethod
    def _get_task_identifier(task_config: ExternalTaskConfig) -> str:
        """Create a readable identifier for a task.

        Args:
            task_config: Task configuration.

        Returns:
            String identifier in format "dag_id.task_id".
        """
        return f"{task_config['external_dag_id']}.{task_config['external_task_id']}"

    def _handle_poke_result(self, ready_tasks: List[str], not_ready_tasks: List[str]) -> bool:
        """Handle the result of the poke operation and log appropriate messages.

        Args:
            ready_tasks: List of task identifiers that are ready.
            not_ready_tasks: List of task identifiers that are not ready.

        Returns:
            True if all tasks are ready, False otherwise.
        """
        if not not_ready_tasks:
            self.log.info("All external tasks completed successfully")
            return True

        self.log.info("Ready task instances: %s", ", ".join(ready_tasks))
        self.log.info("Unready task instances: %s", ", ".join(not_ready_tasks))
        return False
