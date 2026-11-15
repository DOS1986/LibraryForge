import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class ScanJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = ("queued", "Queued")
        DISCOVERING = ("discovering", "Discovering")
        RUNNING = ("running", "Running")
        COMPLETED = ("completed", "Completed")
        COMPLETED_WITH_ERRORS = (
            "completed_with_errors",
            "Completed With Errors",
        )
        FAILED = ("failed", "Failed")
        CANCELLED = ("cancelled", "Cancelled")

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    library = models.ForeignKey(
        "libraries.Library",
        on_delete=models.CASCADE,
        related_name="scan_jobs",
    )

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scan_jobs",
    )

    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )

    total_files = models.PositiveIntegerField(default=0)
    processed_files = models.PositiveIntegerField(default=0)

    total_media_files = models.PositiveIntegerField(default=0)
    processed_media_files = models.PositiveIntegerField(default=0)

    total_nfo_files = models.PositiveIntegerField(default=0)
    processed_nfo_files = models.PositiveIntegerField(default=0)

    current_path = models.TextField(blank=True)

    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)

    nfo_created_count = models.PositiveIntegerField(default=0)
    nfo_updated_count = models.PositiveIntegerField(default=0)

    error_count = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)

    discovery_had_errors = models.BooleanField(default=False)

    # Which ScanWorker claimed this job, so a job whose worker stopped can be
    # recognized as interrupted instead of looking active forever.
    worker_id = models.CharField(max_length=128, blank=True, default="")

    # Set by a user; the worker stops at its next progress checkpoint.
    cancel_requested = models.BooleanField(default=False)

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["library"],
                condition=Q(
                    status__in=[
                        "queued",
                        "discovering",
                        "running",
                    ]
                ),
                name="one_active_scan_per_library",
            ),
        ]

    @property
    def progress_percent(self):
        if self.total_files <= 0:
            return 0

        return min(
            100,
            round(
                (
                    self.processed_files
                    / self.total_files
                )
                * 100,
                1,
            ),
        )

    def __str__(self):
        return (
            f"{self.library.name}: "
            f"{self.get_status_display()}"
        )



class ScanWorker(models.Model):
    """A running scan worker process, kept alive by a heartbeat.

    The web server and the worker are separate processes, so liveness is
    shared through the database. A worker whose heartbeat is older than
    ``jobs.services.WORKER_STALE_SECONDS`` is treated as stopped.
    """

    id = models.CharField(primary_key=True, max_length=128)
    hostname = models.CharField(max_length=255, blank=True)
    pid = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField()
    last_seen_at = models.DateTimeField(db_index=True)
    current_job = models.ForeignKey(
        ScanJob,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["-last_seen_at"]

    def __str__(self):
        return f"{self.hostname}:{self.pid}"
