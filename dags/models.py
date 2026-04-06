"""
Data models for DAG management.

These models store the canonical DAG definitions, run history, and run logs
that are managed by this application and synchronised to the on-prem
Apache Airflow instance.
"""

import uuid

from django.db import models


class DAG(models.Model):
    """
    Represents an Apache Airflow DAG definition managed through this platform.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dag_id = models.CharField(
        max_length=250,
        unique=True,
        db_index=True,
        help_text="The Airflow DAG identifier (e.g. 'etl_daily_sales').",
    )
    name = models.CharField(max_length=500, help_text="Human-readable name.")
    description = models.TextField(blank=True, default="")
    python_script = models.TextField(
        help_text="Full Python source code of the DAG file.",
    )
    schedule_interval = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Cron expression or Airflow preset (e.g. '0 2 * * *', '@daily').",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether the DAG is enabled (un-paused) in Airflow.",
    )
    max_retries = models.IntegerField(
        default=3,
        help_text="Maximum number of retries for failed tasks.",
    )
    retry_delay_seconds = models.IntegerField(
        default=300,
        help_text="Delay in seconds between retries.",
    )
    timeout_seconds = models.IntegerField(
        default=3600,
        help_text="Execution timeout in seconds.",
    )
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text="List of string tags for categorisation.",
    )
    configuration = models.JSONField(
        default=dict,
        blank=True,
        help_text="Arbitrary configuration parameters passed to the DAG.",
    )
    owner = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text="Owner identifier (team or individual).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Azure AD user who created this DAG.",
    )
    updated_by = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Azure AD user who last updated this DAG.",
    )

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "DAG"
        verbose_name_plural = "DAGs"

    def __str__(self) -> str:
        return f"{self.dag_id} ({self.name})"


class DAGRun(models.Model):
    """
    Records an execution run for a DAG, mirroring Airflow's DagRun concept.
    """

    class State(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dag = models.ForeignKey(
        DAG,
        on_delete=models.CASCADE,
        related_name="runs",
    )
    run_id = models.CharField(
        max_length=250,
        help_text="Airflow's unique run identifier.",
    )
    state = models.CharField(
        max_length=20,
        choices=State.choices,
        default=State.QUEUED,
        db_index=True,
    )
    execution_date = models.DateTimeField(
        help_text="Logical execution date for the run.",
    )
    start_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Actual start time.",
    )
    end_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Actual end time.",
    )
    external_trigger = models.BooleanField(
        default=False,
        help_text="Whether this run was triggered externally.",
    )
    conf = models.JSONField(
        default=dict,
        blank=True,
        help_text="Runtime configuration passed when triggering.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-execution_date"]
        verbose_name = "DAG Run"
        verbose_name_plural = "DAG Runs"
        unique_together = [("dag", "run_id")]

    def __str__(self) -> str:
        return f"{self.dag.dag_id} / {self.run_id} [{self.state}]"


class DAGRunLog(models.Model):
    """
    Stores log entries for a specific DAG run.
    """

    class Level(models.TextChoices):
        INFO = "INFO", "Info"
        WARNING = "WARNING", "Warning"
        ERROR = "ERROR", "Error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dag_run = models.ForeignKey(
        DAGRun,
        on_delete=models.CASCADE,
        related_name="logs",
    )
    timestamp = models.DateTimeField(
        help_text="When the log entry was produced.",
    )
    level = models.CharField(
        max_length=10,
        choices=Level.choices,
        default=Level.INFO,
    )
    message = models.TextField()

    class Meta:
        ordering = ["timestamp"]
        verbose_name = "DAG Run Log"
        verbose_name_plural = "DAG Run Logs"

    def __str__(self) -> str:
        return f"[{self.level}] {self.timestamp} — {self.message[:80]}"
