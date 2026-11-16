"""LibraryForge scan worker.

``run_scan_worker`` runs one worker, which scans one library at a time.
``run_scan_worker --workers N`` runs a small supervisor that starts N worker
processes, so up to N libraries scan at once. Each worker claims a different
queued scan (queued jobs are locked with SKIP LOCKED), and there is never
more than one active scan per library.

Separate processes, rather than threads, keep each scan's database
connection and any crash or hang isolated to that scan.
"""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, connection, transaction
from django.utils import timezone

from jobs.models import ScanJob
from jobs.services import (
    HEARTBEAT_SECONDS,
    heartbeat,
    live_worker_ids,
    mark_cancelled,
    new_worker_id,
    prune_dead_workers,
    recover_interrupted_jobs,
    register_worker,
    unregister_worker,
)
from media.services.scanner import ScanCancelled, process_scan_job
from outputs.services.engine import (
    claim_next_run,
    execute_run,
    recover_interrupted_runs,
)

MAX_WORKERS = 8
RESPAWN_DELAY_SECONDS = 5
SHUTDOWN_GRACE_SECONDS = 10


def _restart_requested():
    restart_file = os.environ.get("LIBRARYFORGE_RESTART_FILE", "").strip()
    if not restart_file:
        return False
    return Path(restart_file).exists()


class _Heartbeat(threading.Thread):
    """Records that this worker is alive, even during long scan stages that
    report no progress (for example building the semantic catalog)."""

    def __init__(self, worker_id: str):
        super().__init__(name="scan-worker-heartbeat", daemon=True)
        self.worker_id = worker_id
        self.current_job_id = None
        self.stopping = threading.Event()

    def run(self):
        try:
            while not self.stopping.wait(HEARTBEAT_SECONDS):
                try:
                    heartbeat(self.worker_id, self.current_job_id)
                except Exception:  # noqa: BLE001 - the heartbeat thread must never die
                    # A missed heartbeat is retried; the database may be
                    # briefly unavailable.
                    close_old_connections()
        finally:
            connection.close()


class _SupervisorWatch(threading.Thread):
    """In a supervised child, stdin is a pipe from the supervisor. It closes
    when the supervisor exits, so the child stops instead of running orphaned."""

    def __init__(self):
        super().__init__(name="scan-worker-supervisor-watch", daemon=True)
        self.gone = threading.Event()

    def run(self):
        try:
            while sys.stdin.read(1024):
                pass
        except (OSError, ValueError):
            pass
        self.gone.set()


class Command(BaseCommand):
    help = "Runs the LibraryForge media scan worker. Use --workers N to scan up to N libraries at once."

    def add_arguments(self, parser):
        parser.add_argument(
            "--workers",
            type=int,
            default=None,
            help=(
                "Number of worker processes, 1 to "
                f"{MAX_WORKERS}. Defaults to LIBRARYFORGE_SCAN_WORKERS (1 if unset)."
            ),
        )
        # Internal: set by the supervisor for each child process.
        parser.add_argument("--supervised", action="store_true", help="Internal; used by --workers.")

    def handle(self, *args, **options):
        workers = options["workers"]
        if workers is None:
            workers = int(getattr(settings, "LIBRARYFORGE_SCAN_WORKERS", 1) or 1)
        if not 1 <= workers <= MAX_WORKERS:
            raise CommandError(f"--workers must be between 1 and {MAX_WORKERS}.")

        if options["supervised"]:
            watch = _SupervisorWatch()
            watch.start()
            self._run_worker(stop_event=watch.gone)
        elif workers == 1:
            self._run_worker(stop_event=None)
        else:
            self._supervise(workers)

    # ------------------------------------------------------------------
    # Supervisor
    # ------------------------------------------------------------------

    def _child_command(self) -> list[str]:
        return [sys.executable, str(Path(settings.BASE_DIR) / "manage.py"), "run_scan_worker", "--supervised"]

    def _spawn(self) -> subprocess.Popen:
        # stdin is a pipe the child watches: it closes when this process
        # exits for any reason, which tells the child to stop.
        return subprocess.Popen(self._child_command(), cwd=settings.BASE_DIR, stdin=subprocess.PIPE)

    def _supervise(self, count: int) -> None:
        self.stdout.write(self.style.SUCCESS(f"LibraryForge scan supervisor starting {count} workers."))
        children: dict[int, subprocess.Popen] = {slot: self._spawn() for slot in range(count)}
        respawn_at: dict[int, float] = {}
        stopping = False

        try:
            while True:
                if not stopping and _restart_requested():
                    # Children see the same restart request and exit after
                    # their current scan; wait for all of them.
                    self.stdout.write("Restart requested; waiting for scan workers to finish their current scans.")
                    stopping = True

                for slot, process in list(children.items()):
                    code = process.poll()
                    if code is None:
                        continue
                    del children[slot]
                    if not stopping:
                        self.stderr.write(f"Scan worker {slot + 1} exited (code {code}); restarting it shortly.")
                        respawn_at[slot] = time.monotonic() + RESPAWN_DELAY_SECONDS

                for slot, when in list(respawn_at.items()):
                    if stopping:
                        respawn_at.clear()
                        break
                    if time.monotonic() >= when:
                        del respawn_at[slot]
                        children[slot] = self._spawn()

                if stopping and not children:
                    self.stdout.write("All scan workers stopped.")
                    return

                time.sleep(1)
        except KeyboardInterrupt:
            self.stdout.write("Stopping scan workers...")
        finally:
            self._stop_children(list(children.values()))

    def _stop_children(self, children: list[subprocess.Popen]) -> None:
        # Ctrl+C reaches the children too when they share this console; give
        # them a moment to stop on their own, then make sure they do.
        deadline = time.monotonic() + SHUTDOWN_GRACE_SECONDS
        for process in children:
            if process.stdin:
                try:
                    process.stdin.close()
                except OSError:
                    pass
        for process in children:
            try:
                process.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _run_projection(self, worker_id: str, beat) -> bool:
        """Run one queued projection plan; False if there was none."""

        run = claim_next_run(worker_id)
        if run is None:
            return False
        self.stdout.write(f"Applying projection plan for {run.projection_name}")
        heartbeat(worker_id, None)
        try:
            execute_run(run)
        except Exception as exc:  # noqa: BLE001 - recorded on the run, so the worker keeps going
            run.refresh_from_db()
            run.status = run.Status.FAILED
            run.error = str(exc)[:2000]
            run.completed_at = timezone.now()
            run.save()
            self.stderr.write(self.style.ERROR(str(exc)))
        finally:
            heartbeat(worker_id, None)
        return True

    def _run_worker(self, stop_event: threading.Event | None) -> None:
        worker_id = new_worker_id()
        register_worker(worker_id)
        prune_dead_workers()

        recovered = recover_interrupted_jobs()
        if recovered:
            self.stdout.write(
                f"Marked {recovered} interrupted scan{'s' if recovered != 1 else ''} as failed."
            )

        interrupted = recover_interrupted_runs(live_worker_ids())
        if interrupted:
            self.stdout.write(
                f"Marked {interrupted} interrupted projection run{'s' if interrupted != 1 else ''}."
            )

        beat = _Heartbeat(worker_id)
        beat.start()

        self.stdout.write(
            self.style.SUCCESS("LibraryForge scan worker started.")
        )

        try:
            while True:
                # The development/production supervisor leaves the restart
                # request in place until this worker exits. If a scan was
                # already running, execution only returns here after
                # process_scan_job() has completed, so an active ScanJob is
                # never abandoned in DISCOVERING/RUNNING during a restart.
                if _restart_requested():
                    self.stdout.write(
                        "LibraryForge restart requested; scan worker stopping "
                        "at a safe boundary."
                    )
                    return

                if stop_event is not None and stop_event.is_set():
                    self.stdout.write("Scan supervisor stopped; scan worker stopping.")
                    return

                job_id = None

                with transaction.atomic():
                    job = (
                        ScanJob.objects
                        .select_for_update(skip_locked=True)
                        .filter(status=ScanJob.Status.QUEUED)
                        .order_by("created_at")
                        .first()
                    )

                    if job:
                        job.status = ScanJob.Status.DISCOVERING
                        job.started_at = timezone.now()
                        job.worker_id = worker_id
                        job.save(
                            update_fields=[
                                "status",
                                "started_at",
                                "worker_id",
                                "updated_at",
                            ]
                        )
                        job_id = job.id

                if job_id is None:
                    # No scan waiting: apply a reviewed projection plan, if any.
                    if self._run_projection(worker_id, beat):
                        continue
                    time.sleep(1)
                    continue

                beat.current_job_id = job_id
                heartbeat(worker_id, job_id)
                job = ScanJob.objects.select_related("library").get(pk=job_id)
                self.stdout.write(f"Scanning {job.library.name}")

                try:
                    process_scan_job(job)
                except ScanCancelled:
                    mark_cancelled(job)
                    self.stdout.write(f"Scan of {job.library.name} cancelled.")
                except Exception as exc:
                    job.status = ScanJob.Status.FAILED
                    job.completed_at = timezone.now()
                    job.current_path = ""
                    job.error_count += 1

                    errors = list(job.errors)
                    if len(errors) < 100:
                        errors.append(
                            {
                                "path": job.library.path,
                                "error": str(exc),
                            }
                        )

                    job.errors = errors
                    job.save()
                    self.stderr.write(self.style.ERROR(str(exc)))
                finally:
                    beat.current_job_id = None
                    heartbeat(worker_id, None)

        except KeyboardInterrupt:
            self.stdout.write("Worker stopped.")
        finally:
            beat.stopping.set()
            beat.join(timeout=HEARTBEAT_SECONDS + 5)
            unregister_worker(worker_id)
