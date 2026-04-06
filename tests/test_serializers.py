"""Unit tests for DRF serializers."""

from datetime import datetime, timezone

import pytest

from dags.models import DAG, DAGRun, DAGRunLog
from dags.serializers import (
    DAGListSerializer,
    DAGRunLogSerializer,
    DAGRunSerializer,
    DAGSerializer,
    TriggerDAGRunSerializer,
)


@pytest.mark.django_db
class TestDAGSerializer:
    def test_contains_all_fields(self, sample_dag):
        serializer = DAGSerializer(sample_dag)
        expected_fields = {
            "id", "dag_id", "name", "description", "python_script",
            "schedule_interval", "is_active", "max_retries",
            "retry_delay_seconds", "timeout_seconds", "tags",
            "configuration", "owner", "created_at", "updated_at",
            "created_by", "updated_by",
        }
        assert set(serializer.data.keys()) == expected_fields

    def test_read_only_fields(self):
        serializer = DAGSerializer()
        ro = set(serializer.Meta.read_only_fields)
        assert {"id", "created_at", "updated_at", "created_by", "updated_by"} == ro

    def test_valid_input(self):
        data = {
            "dag_id": "new_dag",
            "name": "New DAG",
            "python_script": "print('new')",
            "schedule_interval": "@daily",
            "is_active": True,
            "max_retries": 2,
            "retry_delay_seconds": 60,
            "timeout_seconds": 1800,
            "tags": ["test"],
            "configuration": {"key": "val"},
            "owner": "owner@test.com",
            "description": "A new dag",
        }
        serializer = DAGSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_missing_required_fields(self):
        serializer = DAGSerializer(data={})
        assert not serializer.is_valid()
        assert "dag_id" in serializer.errors
        assert "name" in serializer.errors


@pytest.mark.django_db
class TestDAGListSerializer:
    def test_subset_fields(self, sample_dag):
        serializer = DAGListSerializer(sample_dag)
        expected = {"id", "dag_id", "name", "schedule_interval", "is_active", "owner", "tags", "updated_at"}
        assert set(serializer.data.keys()) == expected

    def test_does_not_include_script(self, sample_dag):
        serializer = DAGListSerializer(sample_dag)
        assert "python_script" not in serializer.data


@pytest.mark.django_db
class TestDAGRunSerializer:
    def test_fields(self, sample_dag_run):
        serializer = DAGRunSerializer(sample_dag_run)
        assert "dag_id" in serializer.data
        assert serializer.data["dag_id"] == "etl_daily_sales"
        assert serializer.data["state"] == "success"
        assert serializer.data["external_trigger"] is True

    def test_all_expected_fields(self, sample_dag_run):
        serializer = DAGRunSerializer(sample_dag_run)
        expected = {
            "id", "dag", "dag_id", "run_id", "state",
            "execution_date", "start_date", "end_date",
            "external_trigger", "conf", "created_at",
        }
        assert set(serializer.data.keys()) == expected


@pytest.mark.django_db
class TestDAGRunLogSerializer:
    def test_fields(self, sample_dag_run_log):
        serializer = DAGRunLogSerializer(sample_dag_run_log)
        expected = {"id", "dag_run", "timestamp", "level", "message"}
        assert set(serializer.data.keys()) == expected
        assert serializer.data["level"] == "INFO"


class TestTriggerDAGRunSerializer:
    def test_with_conf(self):
        serializer = TriggerDAGRunSerializer(data={"conf": {"key": "val"}})
        assert serializer.is_valid()
        assert serializer.validated_data["conf"] == {"key": "val"}

    def test_without_conf(self):
        serializer = TriggerDAGRunSerializer(data={})
        assert serializer.is_valid()
        assert serializer.validated_data["conf"] == {}

    def test_empty_body(self):
        serializer = TriggerDAGRunSerializer(data={})
        assert serializer.is_valid()
