import time

from django.core.management.base import (
    BaseCommand,
)

from django.db import transaction
from django.utils import timezone

from jobs.models import ScanJob

from media.services.scanner import (
    process_scan_job,
)


class Command(BaseCommand):
    help = (
        "Runs the LibraryForge "
        "media scan worker."
    )

    def handle(
        self,
        *args,
        **options,
    ):
        self.stdout.write(
            self.style.SUCCESS(
                "LibraryForge scan "
                "worker started."
            )
        )

        try:
            while True:
                job_id = None

                with transaction.atomic():
                    job = (
                        ScanJob.objects
                        .select_for_update(
                            skip_locked=True
                        )
                        .filter(
                            status=(
                                ScanJob
                                .Status
                                .QUEUED
                            )
                        )
                        .order_by(
                            "created_at"
                        )
                        .first()
                    )

                    if job:
                        job.status = (
                            ScanJob
                            .Status
                            .DISCOVERING
                        )

                        job.started_at = (
                            timezone.now()
                        )

                        job.save(
                            update_fields=[
                                "status",
                                "started_at",
                                "updated_at",
                            ]
                        )

                        job_id = job.id

                if job_id is None:
                    time.sleep(1)
                    continue

                job = (
                    ScanJob.objects
                    .select_related(
                        "library"
                    )
                    .get(
                        pk=job_id
                    )
                )

                self.stdout.write(
                    f"Scanning "
                    f"{job.library.name}"
                )

                try:
                    process_scan_job(
                        job
                    )

                except Exception as exc:
                    job.status = (
                        ScanJob
                        .Status
                        .FAILED
                    )

                    job.completed_at = (
                        timezone.now()
                    )

                    job.current_path = ""
                    job.error_count += 1

                    errors = list(
                        job.errors
                    )

                    if len(errors) < 100:
                        errors.append(
                            {
                                "path":
                                    job.library.path,

                                "error":
                                    str(exc),
                            }
                        )

                    job.errors = errors
                    job.save()

                    self.stderr.write(
                        self.style.ERROR(
                            str(exc)
                        )
                    )

        except KeyboardInterrupt:
            self.stdout.write(
                "Worker stopped."
            )
