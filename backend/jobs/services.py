"""Scan worker liveness, interrupted-job recovery, and cancellation.

Scans run in a separate worker process (``manage.py run_scan_worker``). The
worker records a heartbeat in the database every few seconds, so the web
server can tell whether queued scans will be picked up and whether an
"active" scan is really still running.
"""

from __future__ import annotations

import os
import socket
import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from jobs.models import ScanJob, ScanWorker

HEARTBEAT_SECONDS = 10
WORKER_STALE_SECONDS = 60

ACTIVE_STATUSES = (
    ScanJob.Status.QUEUED,
    ScanJob.Status.DISCOVERING,
    ScanJob.Status.RUNNING,
)
RUNNING_STATUSES = (ScanJob.Status.DISCOVERING, ScanJob.Status.RUNNING)

INTERRUPTED_MESSAGE = "Interrupted: the scan worker stopped before this scan finished. Start a new scan."
CANCELLED_MESSAGE = "Cancelled before finishing. Files already processed keep their updated details."


def new_worker_id() -> str:
    return f"{socket.gethostname()[:80]}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def register_worker(worker_id: str) -> ScanWorker:
    now = timezone.now()
    worker, _created = ScanWorker.objects.update_or_create(
        id=worker_id,
        defaults={
            "hostname": socket.gethostname()[:255],
            "pid": os.getpid(),
            "started_at": now,
            "last_seen_at": now,
            "current_job": None,
        },
    )
    return worker


def heartbeat(worker_id: str, current_job_id=None) -> None:
    updated = ScanWorker.objects.filter(id=worker_id).update(
        last_seen_at=timezone.now(), current_job_id=current_job_id
    )
    if not updated:
        register_worker(worker_id)
        ScanWorker.objects.filter(id=worker_id).update(current_job_id=current_job_id)


def unregister_worker(worker_id: str) -> None:
    ScanWorker.objects.filter(id=worker_id).delete()


def live_worker_ids() -> set[str]:
    cutoff = timezone.now() - timedelta(seconds=WORKER_STALE_SECONDS)
    return set(ScanWorker.objects.filter(last_seen_at__gte=cutoff).values_list("id", flat=True))


def prune_dead_workers() -> None:
    cutoff = timezone.now() - timedelta(seconds=WORKER_STALE_SECONDS * 10)
    ScanWorker.objects.filter(last_seen_at__lt=cutoff).delete()


def is_stalled(job: ScanJob, live: set[str] | None = None) -> bool:
    """A discovering/running job whose worker is no longer alive."""

    if job.status not in RUNNING_STATUSES:
        return False
    live = live_worker_ids() if live is None else live
    return job.worker_id not in live


def _finish(job: ScanJob, status: str, message: str) -> None:
    job.status = status
    job.completed_at = timezone.now()
    job.current_path = ""
    errors = list(job.errors or [])
    if len(errors) < 100:
        errors.append({"path": "", "error": message})
    job.errors = errors
    if status == ScanJob.Status.FAILED:
        job.error_count += 1
    job.save(update_fields=["status", "completed_at", "current_path", "errors", "error_count", "updated_at"])


def recover_interrupted_jobs(live: set[str] | None = None) -> int:
    """Mark discovering/running jobs whose worker is gone as failed."""

    live = live_worker_ids() if live is None else live
    recovered = 0
    with transaction.atomic():
        for job in ScanJob.objects.select_for_update(skip_locked=True).filter(status__in=RUNNING_STATUSES):
            if job.worker_id not in live:
                _finish(job, ScanJob.Status.FAILED, INTERRUPTED_MESSAGE)
                recovered += 1
    return recovered


def cancel_job(job: ScanJob) -> ScanJob:
    """Cancel a scan. Queued or stalled scans stop now; a running scan stops
    at its worker's next progress checkpoint."""

    with transaction.atomic():
        job = ScanJob.objects.select_for_update().get(pk=job.pk)
        if job.status not in ACTIVE_STATUSES:
            return job
        if job.status == ScanJob.Status.QUEUED:
            _finish(job, ScanJob.Status.CANCELLED, "Cancelled before it started.")
        elif is_stalled(job):
            _finish(job, ScanJob.Status.FAILED, INTERRUPTED_MESSAGE)
        else:
            job.cancel_requested = True
            job.save(update_fields=["cancel_requested", "updated_at"])
    return job


def mark_cancelled(job: ScanJob) -> None:
    job.refresh_from_db()
    _finish(job, ScanJob.Status.CANCELLED, CANCELLED_MESSAGE)


def worker_status() -> dict:
    live = live_worker_ids()
    workers = ScanWorker.objects.filter(id__in=live).select_related("current_job__library")
    return {
        "alive": bool(live),
        "stale_after_seconds": WORKER_STALE_SECONDS,
        "workers": [
            {
                "id": worker.id,
                "hostname": worker.hostname,
                "pid": worker.pid,
                "started_at": worker.started_at,
                "last_seen_at": worker.last_seen_at,
                "current_job": str(worker.current_job_id) if worker.current_job_id else None,
                "current_library": worker.current_job.library.name if worker.current_job_id else None,
            }
            for worker in workers
        ],
        "queued_jobs": ScanJob.objects.filter(status=ScanJob.Status.QUEUED).count(),
    }
