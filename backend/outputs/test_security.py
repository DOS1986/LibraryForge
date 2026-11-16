"""Projection folders are confined to the allowed output roots before any
use of the disk, and messages shown to users are LibraryForge's own."""

import os
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock, skipUnless

from django.test import SimpleTestCase, override_settings

from metadata.services.provider_match import MatchRequestError
from outputs.security import (
    NO_OUTPUT_ROOTS,
    OUTSIDE_OUTPUT_ROOTS,
    ProjectionSecurityError,
    confined_output_folder,
)
from outputs.services import fileops
from outputs.test_cleanup import _Movies


class ConfinedOutputFolderTests(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = self.tmp / "out"
        self.root.mkdir()
        patch = override_settings(LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS=[str(self.root)])
        patch.enable()
        self.addCleanup(patch.disable)

    def refused(self, value, message=OUTSIDE_OUTPUT_ROOTS):
        with self.assertRaises(ProjectionSecurityError) as caught:
            confined_output_folder(value)
        self.assertEqual(caught.exception.message, message)

    def test_folders_inside_a_root_and_the_root_itself_are_allowed(self):
        self.assertEqual(confined_output_folder(str(self.root / "Movies")), self.root / "Movies")
        self.assertEqual(confined_output_folder(str(self.root)), self.root)

    def test_folders_outside_every_root_are_refused(self):
        self.refused(str(self.tmp / "elsewhere"))
        # Shares a prefix with the root's name, but isn't inside it.
        self.refused(str(self.tmp / "out-other"))
        self.refused(str(self.root / ".." / "escaped"))
        self.refused("   ", "Projection destination path is required.")

    def test_no_roots_configured(self):
        with override_settings(LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS=[]):
            self.refused(str(self.root / "Movies"), NO_OUTPUT_ROOTS)

    def test_a_path_outside_the_roots_is_never_looked_up_on_disk(self):
        with mock.patch("outputs.security.os.path.realpath") as realpath:
            self.refused(str(self.tmp / "elsewhere"))
        realpath.assert_not_called()

    def test_a_link_inside_a_root_cannot_lead_out_of_it(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        link = self.root / "link"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("This system can't create symbolic links.")
        self.refused(str(link / "Movies"))

    def test_a_root_that_does_not_exist_yet_can_be_the_folder(self):
        new = self.tmp / "new"
        with override_settings(LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS=[str(new)]):
            self.assertEqual(confined_output_folder(str(new)), new)
            self.assertEqual(confined_output_folder(str(new / "Shows")), new / "Shows")

    @skipUnless(os.name == "nt", "Only Windows folder names ignore letter case.")
    def test_case_differences_are_allowed_where_names_ignore_case(self):
        spelled = str(self.root).swapcase() + os.sep + "Movies"
        self.assertEqual(confined_output_folder(spelled), self.root / "Movies")


class DestinationUseTests(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = self.tmp / "out"
        self.root.mkdir()
        patch = override_settings(LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS=[str(self.root)])
        patch.enable()
        self.addCleanup(patch.disable)

    def test_destination_error_reports_a_folder_outside_the_roots(self):
        projection = SimpleNamespace(destination_path=str(self.tmp / "elsewhere"))
        self.assertEqual(fileops.destination_error(projection), OUTSIDE_OUTPUT_ROOTS)
        self.assertIsNone(fileops.destination_error(SimpleNamespace(destination_path=str(self.root / "Shows"))))

    def test_destination_root_never_creates_a_folder_outside_the_roots(self):
        outside = self.tmp / "elsewhere"
        with self.assertRaises(MatchRequestError) as caught:
            fileops._destination_root(SimpleNamespace(destination_path=str(outside)))
        self.assertEqual(caught.exception.message, OUTSIDE_OUTPUT_ROOTS)
        self.assertFalse(outside.exists())

        inside = self.root / "Shows"
        self.assertEqual(fileops._destination_root(SimpleNamespace(destination_path=str(inside))), inside)
        self.assertTrue(inside.is_dir())

    def test_folder_problem_uses_its_own_wording(self):
        error = OSError(13, "Access is denied")
        self.assertEqual(fileops.folder_problem(error), "The output folder can't be reached (Access is denied).")


class XmlTextTests(SimpleTestCase):
    def test_characters_xml_does_not_allow_are_removed(self):
        self.assertEqual(fileops._clean("A\x00B\x08C\x0bD\x1fE￾F￿"), "ABCDEF")
        self.assertEqual(fileops._clean("tab\tnew\nline\rkept é ✓"), "tab\tnew\nline\rkept é ✓")


class PlanOutsideRootsTests(_Movies):
    def test_a_folder_no_longer_inside_a_root_is_blocked_without_being_looked_at(self):
        projection = self.create(self.movies)
        elsewhere = self.tmp / "new-root"
        with (
            override_settings(LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS=[str(elsewhere)]),
            mock.patch("outputs.services.fileops.destination_error") as destination_error,
        ):
            plan = self.plan(projection)
        codes = [finding["code"] for finding in plan["findings"]]
        self.assertEqual(plan["status"], "blocked")
        self.assertIn("OUTSIDE_OUTPUT_ROOT", codes)
        self.assertNotIn("DESTINATION_UNAVAILABLE", codes)
        destination_error.assert_not_called()
        message = next(f["message"] for f in plan["findings"] if f["code"] == "OUTSIDE_OUTPUT_ROOT")
        self.assertEqual(message, OUTSIDE_OUTPUT_ROOTS)


class WorkerCrashMessageTests(_Movies):
    def test_an_unexpected_error_is_recorded_without_its_text(self):
        import io

        from jobs.management.commands.run_scan_worker import Command
        from outputs.models import ProjectionRun

        projection = self.create(self.movies)
        plan = self.plan(projection)
        queued = self.client.post(
            f"/api/projection-plans/{plan['id']}/runs/",
            {"digest": plan["digest"], "idempotency_key": "crash-1"},
            format="json",
        )
        self.assertEqual(queued.status_code, 202, queued.data)

        command = Command(stdout=io.StringIO(), stderr=io.StringIO())
        with mock.patch(
            "jobs.management.commands.run_scan_worker.execute_run", side_effect=RuntimeError("secret detail")
        ):
            self.assertTrue(command._run_projection("worker-1", None))

        run = ProjectionRun.objects.get(id=queued.data["id"])
        self.assertEqual(run.status, ProjectionRun.Status.FAILED)
        self.assertNotIn("secret detail", run.error)
        self.assertIn("unexpected error", run.error)
        self.assertIn("secret detail", command.stderr._out.getvalue())
