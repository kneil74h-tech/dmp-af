from typing import TYPE_CHECKING, Optional, Callable, Any

from airflow import Dataset
from airflow.lineage import prepare_lineage, apply_lineage
from airflow.utils.operator_helpers import ExecutionCallableRunner
from dmp_af.common.constants import DBT_MODEL_DAG_PARAM
from dmp_af.common.utils import build_dbt_run_model_bash_extra_options
from dmp_af.operators.base import DbtBaseActionOperator
from airflow.utils.context import context_get_outlet_events
if TYPE_CHECKING:
    from airflow.utils.context import Context
    from dmp_af.conf import Config

TaskPreExecuteHook = Callable[['Context', 'Config'], None]
TaskPostExecuteHook = Callable[['Context', 'Config', Any], None]

class DbtBaseDatasetOperator(DbtBaseActionOperator):
    def __init__(self, model_name: Optional[str], is_dataset_enable=False, model_type: str = 'sql', **kwargs) -> None:
        if model_name:
            # exactly one model
            super().__init__(
                model_name=model_name,
                model_type=model_type,
                outlets=[Dataset(model_name)] if is_dataset_enable else [],
                **kwargs,
            )
        else:
            super().__init__(model_name=DBT_MODEL_DAG_PARAM, **kwargs)

    def execute(self, context: 'Context'):
        if 'params' in context:
            if DBT_MODEL_DAG_PARAM in context['params'] and self.model_name == DBT_MODEL_DAG_PARAM:
                # handle case for dbt_run_model DAG
                self.bash_options['--select'] = context['params'][DBT_MODEL_DAG_PARAM]

                bash_options, bash_flags = build_dbt_run_model_bash_extra_options(context['params'])
                self.bash_options.update(bash_options)
                self.bash_flags.update(bash_flags)

        super().execute(context)

    def _patch_path_to_dbt_bash(self, **kwargs):
        if self.model_name_wo_type == DBT_MODEL_DAG_PARAM:
            return 'PATH_TO_DBT=$DBT_PROJECT_DIR && '
        return super()._patch_path_to_dbt_bash(**kwargs)


class DbtRun(DbtBaseDatasetOperator):
    @property
    def cli_command(self) -> str:
        return 'run'

    def __init__(
        self,
        dmp_af_config: 'Config',
        pre_execute: TaskPreExecuteHook | None = None,
        post_execute: TaskPostExecuteHook | None = None,
        **kwargs
    ) -> None:
        super().__init__(
            dmp_af_config=dmp_af_config,
            retry_policy=dmp_af_config.retries_config.dbt_run_retry_policy,
            **kwargs,
        )
        self._pre_execute_hook = pre_execute
        self._post_execute_hook = post_execute

    @prepare_lineage
    def pre_execute(self, context: Any):
        """Execute right before self.execute() is called."""
        if self._pre_execute_hook is None:
            return
        ExecutionCallableRunner(
            self._pre_execute_hook,
            context_get_outlet_events(context),
            logger=self.log,
        ).run(context, self.dmp_af_config)

    @apply_lineage
    def post_execute(self, context: Any, result: Any = None):
        """
        Execute right after self.execute() is called.

        It is passed the execution context and any results returned by the operator.
        """
        if self._post_execute_hook is None:
            return
        ExecutionCallableRunner(
            self._post_execute_hook,
            context_get_outlet_events(context),
            logger=self.log,
        ).run(context, self.dmp_af_config, result)


class DbtSeed(DbtBaseDatasetOperator):
    @property
    def cli_command(self) -> str:
        return 'seed'

    def __init__(self, dmp_af_config: 'Config', **kwargs) -> None:
        super().__init__(
            dmp_af_config=dmp_af_config,
            retry_policy=dmp_af_config.retries_config.dbt_seed_retry_policy,
            **kwargs,
        )


class DbtSnapshot(DbtBaseDatasetOperator):
    @property
    def cli_command(self) -> str:
        return 'snapshot'

    def __init__(self, dmp_af_config: 'Config', **kwargs) -> None:
        kwargs.pop('model_type', None)  # Remove if present
        super().__init__(
            dmp_af_config=dmp_af_config,
            model_type='',
            retry_policy=dmp_af_config.retries_config.dbt_snapshot_retry_policy,
            **kwargs,
        )


class DbtTest(DbtBaseActionOperator):
    @property
    def cli_command(self) -> str:
        return 'test'

    def __init__(
        self,
        dmp_af_config: 'Config',
        target_environment: str,
        **kwargs
    ) -> None:
        super().__init__(
            dmp_af_config=dmp_af_config,
            max_active_tis_per_dag=None,
            target_environment=target_environment or dmp_af_config.dbt_default_targets.default_target,
            retry_policy=dmp_af_config.retries_config.dbt_test_retry_policy,
            overlap=True,
            **kwargs,
        )
