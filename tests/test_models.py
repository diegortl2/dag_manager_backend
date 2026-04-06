"""Unit tests for DAG Manager models."""

import uuid
from datetime import datetime, timezone

import pytest

from audit.models import AuditLog
from dags.models import DAG, DAGRun, DAGRunLog


@pytest.mark.django_db
class TestDAGModel:
    def test_create_dag(self, sample_dag):
        assert isinstance(sample_dag.id, uuid.UUID)
        assert sample_dag.dag_id == "etl_daily_sales"
        assert sample_dag.name == "ETL Daily Sales"
        assert sample_dag.is_active is True
        assert sample_dag.max_retries == 3
        assert sample_dag.tags == ["etl", "sales"]

    def test_str_representation(self, sample_dag):
        assert str(sample_dag) == "etl_daily_sales (ETL Daily Sales)"

    def test_default_values(self):
        dag = DAG.objects.create(
            dag_id="minimal_dag",
            name="Minimal",
            python_script="print('hello')",
        )
        assert dag.is_active is True
        assert dag.max_retries == 3
        assert dag.retry_delay_seconds == 300
        assert dag.timeout_seconds == 3600
        assert dag.tags == []
        assert dag.configuration == {}
        assert dag.description == ""
        assert dag.owner == ""

    def test_unique_dag_id(self, sample_dag):
        with pytest.raises(Exception):
            DAG.objects.create(
                dag_id=sample_dag.dag_id,
                name="Duplicate",
                python_script="print('dup')",
            )

    def test_ordering_by_updated_at(self, sample_dag, inactive_dag):
        dags = list(DAG.objects.all())
        assert dags[0].updated_at >= dags[1].updated_at

    def test_timestamps_auto_set(self, sample_dag):
        assert sample_dag.created_at is not None
        assert sample_dag.updated_at is not None


@pytest.mark.django_db
class TestDAGRunModel:
    def test_create_dag_run(self, sample_dag_run):
        assert isinstance(sample_dag_run.id, uuid.UUID)
        assert sample_dag_run.state == DAGRun.State.SUCCESS
        assert sample_dag_run.external_trigger is True
        assert sample_dag_run.conf == {"param1": "value1"}

    def test_str_representation(self, sample_dag_run):
        result = str(sample_dag_run)
        assert "etl_daily_sales" in result
        assert "success" in result

    def test_state_choices(self):
        choices = [c[0] for c in DAGRun.State.choices]
        assert "queued" in choices
        assert "running" in choices
        assert "success" in choices
        assert "failed" in choices
        assert "skipped" in choices

    def test_cascade_delete(self, sample_dag, sample_dag_run):
        dag_id = sample_dag.id
        sample_dag.delete()
        assert not DAGRun.objects.filter(dag_id=dag_id).exists()

    def test_ordering_by_execution_date(self, sample_dag):
        run1 = DAGRun.objects.create(
            dag=sample_dag,
            run_id="run_1",
            execution_date=datetime(2024, 1, 10, tzinfo=timezone.utc),
        )
        run2 = DAGRun.objects.create(
            dag=sample_dag,
            run_id="run_2",
            execution_date=datetime(2024, 1, 20, tzinfo=timezone.utc),
        )
        runs = list(DAGRun.objects.filter(dag=sample_dag))
        assert runs[0].execution_date > runs[1].execution_date


@pytest.mark.django_db
class TestDAGRunLogModel:
    def test_create_log(self, sample_dag_run_log):
        assert isinstance(sample_dag_run_log.id, uuid.UUID)
        assert sample_dag_run_log.level == DAGRunLog.Level.INFO
        assert "completed successfully" in sample_dag_run_log.message

    def test_str_representation(self, sample_dag_run_log):
        result = str(sample_dag_run_log)
        assert "[INFO]" in result

    def test_level_choices(self):
        choices = [c[0] for c in DAGRunLog.Level.choices]
        assert "INFO" in choices
        assert "WARNING" in choices
        assert "ERROR" in choices

    def test_ordering_by_timestamp(self, sample_dag_run):
        log1 = DAGRunLog.objects.create(
            dag_run=sample_dag_run,
            timestamp=datetime(2024, 1, 15, 10, 1, tzinfo=timezone.utc),
            level="INFO",
            message="First",
        )
        log2 = DAGRunLog.objects.create(
            dag_run=sample_dag_run,
            timestamp=datetime(2024, 1, 15, 10, 2, tzinfo=timezone.utc),
            level="ERROR",
            message="Second",
        )
        logs = list(DAGRunLog.objects.filter(dag_run=sample_dag_run))
        assert logs[0].timestamp < logs[1].timestamp

    def test_cascade_delete_from_run(self, sample_dag_run, sample_dag_run_log):
        run_id = sample_dag_run.id
        sample_dag_run.delete()
        assert not DAGRunLog.objects.filter(dag_run_id=run_id).exists()


@pytest.mark.django_db
class TestAuditLogModel:
    def test_create_audit_log(self, sample_audit_log):
        assert isinstance(sample_audit_log.id, uuid.UUID)
        assert sample_audit_log.action == AuditLog.Action.CREATE
        assert sample_audit_log.resource_type == "DAG"
        assert sample_audit_log.user == "test@example.com"

    def test_str_representation(self, sample_audit_log):
        result = str(sample_audit_log)
        assert "CREATE" in result
        assert "DAG" in result

    def test_action_choices(self):
        choices = [c[0] for c in AuditLog.Action.choices]
        assert set(choices) == {"CREATE", "UPDATE", "DELETE", "TRIGGER", "PAUSE", "UNPAUSE"}

    def test_ordering_by_timestamp(self):
        log1 = AuditLog.objects.create(
            user="a@test.com", action="CREATE",
            resource_type="DAG", resource_id="1",
        )
        log2 = AuditLog.objects.create(
            user="b@test.com", action="UPDATE",
            resource_type="DAG", resource_id="2",
        )
        logs = list(AuditLog.objects.all())
        assert logs[0].timestamp >= logs[1].timestamp

    def test_changes_jsonfield(self, sample_audit_log):
        assert "after" in sample_audit_log.changes
        assert sample_audit_log.changes["after"]["dag_id"] == "etl_daily_sales"
