"""Scan worker liveness, interrupted-scan recovery, and cancellation."""

import io
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APITestCase

from jobs.models import ScanJob, ScanWorker
from jobs.services import (
    INTERRUPTED_MESSAGE,
    cancel_job,
    is_stalled,
    live_worker_ids,
    recover_interrupted_jobs,
    register_worker,
)
from libraries.models import Library
from media.services.scanner import ScanCancelled, _raise_if_cancelled


class _JobTestCase(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(email="owner@example.com", password="password")
        self.other = user_model.objects.create_user(email="other@example.com", password="password")
        self.client.force_authenticate(self.user)
        self.library = Library.objects.create(owner=self.user, name="TV", path="/tv", content_type="tv")

    def job(self, status=ScanJob.Status.QUEUED, worker_id="", library=None):
        return ScanJob.objects.create(library=library or self.library, status=status, worker_id=worker_id)

    def dead_worker(self, worker_id="dead:1"):
        register_worker(worker_id)
        ScanWorker.objects.filter(id=worker_id).update(last_seen_at=timezone.now() - timedelta(minutes=5))
        return worker_id


class LivenessTests(_JobTestCase):
    def test_heartbeat_age_decides_liveness(self):
        register_worker("live:1")
        dead = self.dead_worker()
        self.assertEqual(live_worker_ids(), {"live:1"})
        self.assertNotIn(dead, live_worker_ids())

    def test_stalled_only_when_running_without_a_live_worker(self):
        register_worker("live:1")
        dead = self.dead_worker()
        self.assertTrue(is_stalled(self.job(ScanJob.Status.RUNNING, dead)))
        self.assertTrue(is_stalled(self.job(ScanJob.Status.DISCOVERING, "", library=self._other_library())))
        self.assertFalse(is_stalled(self.job(ScanJob.Status.RUNNING, "live:1", library=self._other_library())))
        self.assertFalse(is_stalled(self.job(ScanJob.Status.QUEUED, library=self._other_library())))

    def _other_library(self):
        return Library.objects.create(owner=self.user, name="X", path=f"/x{ScanJob.objects.count()}", content_type="tv")


class RecoveryTests(_JobTestCase):
    def test_interrupted_scans_are_failed_and_live_ones_kept(self):
        register_worker("live:1")
        orphan = self.job(ScanJob.Status.RUNNING, self.dead_worker())
        other_library = Library.objects.create(owner=self.user, name="M", path="/m", content_type="movies")
        healthy = self.job(ScanJob.Status.RUNNING, "live:1", library=other_library)
        self.assertEqual(recover_interrupted_jobs(), 1)
        orphan.refresh_from_db()
        healthy.refresh_from_db()
        self.assertEqual(orphan.status, ScanJob.Status.FAILED)
        self.assertEqual(orphan.errors[-1]["error"], INTERRUPTED_MESSAGE)
        self.assertIsNotNone(orphan.completed_at)
        self.assertEqual(healthy.status, ScanJob.Status.RUNNING)


class CancelTests(_JobTestCase):
    def test_cancel_queued_running_stalled_and_finished(self):
        queued = cancel_job(self.job())
        self.assertEqual(queued.status, ScanJob.Status.CANCELLED)

        register_worker("live:1")
        running = cancel_job(self.job(ScanJob.Status.RUNNING, "live:1"))
        self.assertEqual(running.status, ScanJob.Status.RUNNING)
        self.assertTrue(running.cancel_requested)
        running.status = ScanJob.Status.COMPLETED
        running.save()

        stalled = cancel_job(self.job(ScanJob.Status.RUNNING, self.dead_worker()))
        self.assertEqual(stalled.status, ScanJob.Status.FAILED)

        done = cancel_job(stalled)
        self.assertEqual(done.status, ScanJob.Status.FAILED)

    def test_scanner_checkpoint_raises_after_cancel(self):
        register_worker("live:1")
        job = self.job(ScanJob.Status.RUNNING, "live:1")
        _raise_if_cancelled(job)
        cancel_job(job)
        with self.assertRaises(ScanCancelled):
            _raise_if_cancelled(job)


class ApiTests(_JobTestCase):
    def test_job_flags_explain_waiting_and_stalled(self):
        queued = self.job()
        data = self.client.get(f"/api/scan-jobs/{queued.id}/").data
        self.assertTrue(data["waiting_for_worker"])
        self.assertFalse(data["stalled"])
        register_worker("live:1")
        data = self.client.get(f"/api/scan-jobs/{queued.id}/").data
        self.assertFalse(data["waiting_for_worker"])

        queued.status = ScanJob.Status.RUNNING
        queued.worker_id = self.dead_worker()
        queued.save()
        data = self.client.get(f"/api/scan-jobs/{queued.id}/").data
        self.assertTrue(data["stalled"])

    def test_cancel_endpoint_is_owner_scoped(self):
        job = self.job()
        theirs_library = Library.objects.create(owner=self.other, name="T", path="/t", content_type="tv")
        theirs = self.job(library=theirs_library)
        self.assertEqual(self.client.post(f"/api/scan-jobs/{theirs.id}/cancel/").status_code, 404)
        response = self.client.post(f"/api/scan-jobs/{job.id}/cancel/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "cancelled")

    def test_worker_status_counts_only_own_queued_jobs(self):
        self.job()
        theirs_library = Library.objects.create(owner=self.other, name="T", path="/t", content_type="tv")
        self.job(library=theirs_library)
        data = self.client.get("/api/scan-jobs/worker/").data
        self.assertFalse(data["alive"])
        self.assertEqual(data["queued_jobs"], 1)
        register_worker("live:1")
        self.assertTrue(self.client.get("/api/scan-jobs/worker/").data["alive"])

    def test_stalled_scan_no_longer_blocks_new_scans(self):
        stuck = self.job(ScanJob.Status.RUNNING, self.dead_worker())
        response = self.client.post(f"/api/libraries/{self.library.id}/scan/")
        self.assertEqual(response.status_code, 202, response.data)
        self.assertNotEqual(response.data["id"], str(stuck.id))
        stuck.refresh_from_db()
        self.assertEqual(stuck.status, ScanJob.Status.FAILED)

    def test_healthy_active_scan_is_returned_not_duplicated(self):
        register_worker("live:1")
        running = self.job(ScanJob.Status.RUNNING, "live:1")
        response = self.client.post(f"/api/libraries/{self.library.id}/scan/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], str(running.id))


class WorkerCommandTests(_JobTestCase):
    def test_worker_claims_job_handles_cancel_and_unregisters(self):
        orphan_library = Library.objects.create(owner=self.user, name="O", path="/o", content_type="tv")
        orphan = self.job(ScanJob.Status.RUNNING, self.dead_worker(), library=orphan_library)
        queued = self.job()
        claimed = {}

        def fake_scan(job):
            claimed["worker_id"] = ScanJob.objects.get(pk=job.pk).worker_id
            raise ScanCancelled()

        with (
            patch("jobs.management.commands.run_scan_worker.process_scan_job", side_effect=fake_scan),
            patch("jobs.management.commands.run_scan_worker._restart_requested", side_effect=[False, True]),
        ):
            call_command("run_scan_worker", stdout=io.StringIO())

        queued.refresh_from_db()
        orphan.refresh_from_db()
        self.assertEqual(queued.status, ScanJob.Status.CANCELLED)
        self.assertTrue(claimed["worker_id"])
        self.assertEqual(orphan.status, ScanJob.Status.FAILED)
        self.assertFalse(ScanWorker.objects.filter(id=claimed["worker_id"]).exists())


class _FakeProcess:
    """Stands in for a worker subprocess; never starts a real process."""

    def __init__(self, exit_after_polls=None, code=0):
        self.exit_after_polls = exit_after_polls
        self.code = code
        self.polls = 0
        self.stdin = io.StringIO()
        self.terminated = False

    def poll(self):
        self.polls += 1
        if self.exit_after_polls is not None and self.polls > self.exit_after_polls:
            return self.code
        return None

    def wait(self, timeout=None):
        return self.code

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.terminated = True


class WorkerCountTests(_JobTestCase):
    def test_worker_count_is_validated(self):
        from django.core.management.base import CommandError

        for count in (0, 9, -1):
            with self.subTest(count=count), self.assertRaises(CommandError):
                call_command("run_scan_worker", workers=count, stdout=io.StringIO())

    def test_default_comes_from_settings(self):
        from django.test import override_settings

        target = "jobs.management.commands.run_scan_worker.Command"
        with patch(f"{target}._supervise") as supervise, patch(f"{target}._run_worker") as run_worker:
            with override_settings(LIBRARYFORGE_SCAN_WORKERS=3):
                call_command("run_scan_worker", stdout=io.StringIO())
            supervise.assert_called_once_with(3)
            run_worker.assert_not_called()
            with override_settings(LIBRARYFORGE_SCAN_WORKERS=1):
                call_command("run_scan_worker", stdout=io.StringIO())
            run_worker.assert_called_once_with(stop_event=None)
            call_command("run_scan_worker", workers=2, stdout=io.StringIO())
            supervise.assert_called_with(2)

    def test_supervisor_respawns_crashed_worker_and_drains_on_restart(self):
        from jobs.management.commands import run_scan_worker as module

        crashing = _FakeProcess(exit_after_polls=1, code=1)
        steady = _FakeProcess(exit_after_polls=5)
        replacement = _FakeProcess(exit_after_polls=3)
        spawned = [crashing, steady, replacement]
        restart_checks = iter([False, False, False, True, True, True, True, True, True, True])

        with (
            patch.object(module.Command, "_spawn", side_effect=lambda: spawned.pop(0)),
            patch.object(module, "_restart_requested", side_effect=lambda: next(restart_checks)),
            patch.object(module, "RESPAWN_DELAY_SECONDS", 0),
            patch.object(module.time, "sleep"),
        ):
            stdout, stderr = io.StringIO(), io.StringIO()
            command = module.Command(stdout=stdout, stderr=stderr)
            command._supervise(2)

        self.assertEqual(spawned, [])  # the crashed worker was replaced
        self.assertIn("exited (code 1)", stderr.getvalue())
        self.assertIn("All scan workers stopped.", stdout.getvalue())

    def test_supervised_worker_stops_when_supervisor_goes_away(self):
        import threading

        from jobs.management.commands.run_scan_worker import Command, _SupervisorWatch

        gone = threading.Event()
        gone.set()
        queued = self.job()
        stdout = io.StringIO()
        Command(stdout=stdout)._run_worker(stop_event=gone)
        queued.refresh_from_db()
        self.assertEqual(queued.status, ScanJob.Status.QUEUED)  # not claimed
        self.assertIn("Scan supervisor stopped", stdout.getvalue())
        self.assertEqual(ScanWorker.objects.count(), 0)

        watch = _SupervisorWatch()
        with patch("sys.stdin", io.StringIO("still here")):
            watch.run()
        self.assertTrue(watch.gone.is_set())

    def test_child_command_runs_supervised_worker(self):
        from jobs.management.commands.run_scan_worker import Command

        command = Command()._child_command()
        self.assertEqual(command[-2:], ["run_scan_worker", "--supervised"])
        self.assertTrue(command[1].endswith("manage.py"))
