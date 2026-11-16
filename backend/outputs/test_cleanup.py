"""Cleanup reviews and the Outputs page."""

import datetime
import os
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import override_settings

from catalog.models import ArtworkFile
from jobs.models import ScanJob
from libraries.models import Library
from media.models import MediaFile, MediaItem
from outputs.models import OutputProfile, Projection, ProjectionFile, ProjectionRun
from outputs.test_library_nfo import FOLDER_ART, _InPlace
from outputs.test_movies_tv import _Base


class _Movies(_Base):
    def setUp(self):
        super().setUp()
        self.movies = self.library("Movies", "movies")
        self.matrix = MediaItem.objects.create(
            library=self.movies, title="The Matrix", media_type=MediaItem.MediaType.MOVIE, content_rating="R",
            release_date=datetime.date(1999, 3, 31),
        )
        self.matrix_file = self.file(self.movies, self.matrix, "matrix/the.matrix.1999.mkv")
        self.art(self.movies, ArtworkFile.TargetType.MEDIA_ITEM, self.matrix.id, "matrix/poster.jpg")
        self.folder = self.tmp / "out" / "out" / "The Matrix (1999)"

    def cleanup(self, projection):
        return self.plan(projection, cleanup=True)


class CleanupTests(_Movies):
    def test_removes_files_a_keep_policy_held_on_to(self):
        projection = self.create(self.movies, stale_policy="keep")
        Projection.objects.filter(pk=projection.pk).update(stale_policy="keep")
        self.apply(projection)
        MediaFile.objects.filter(pk=self.matrix_file.pk).update(is_present=False)

        regular = self.plan(projection)
        self.assertEqual(regular["counts"], {"retain": 3})
        self.assertEqual(regular["changes"], 0)

        cleanup = self.cleanup(projection)
        self.assertEqual(cleanup["scope"], {"cleanup": True})
        self.assertEqual(cleanup["counts"], {"delete": 3})
        self.assertEqual(cleanup["overview"]["cleanup"]["stale"], 3)
        run = self.client.post(
            f"/api/projection-plans/{cleanup['id']}/runs/",
            {"digest": cleanup["digest"], "idempotency_key": "cleanup-1"},
            format="json",
        )
        self.assertEqual(run.status_code, 202, run.data)
        from outputs.services.engine import execute_run, run_detail

        result = run_detail(execute_run(ProjectionRun.objects.get(id=run.data["id"])))
        self.assertEqual(result["counts"], {"deleted": 3}, result)
        self.assertFalse(self.folder.exists())
        self.assertTrue(Path(self.movies.path, "matrix/the.matrix.1999.mkv").exists())
        self.assertEqual(self.plan(projection)["total"], 0)

    def test_kept_files_stay_while_the_scan_is_incomplete(self):
        projection = self.create(self.movies)
        Projection.objects.filter(pk=projection.pk).update(stale_policy="keep")
        self.apply(projection)
        MediaFile.objects.filter(pk=self.matrix_file.pk).update(is_present=False)
        ScanJob.objects.create(library=self.movies, status=ScanJob.Status.FAILED)

        cleanup = self.cleanup(projection)

        self.assertEqual(cleanup["counts"], {"retain": 3})
        self.assertEqual(cleanup["changes"], 0)
        self.assertIn("STALE_KEPT", {finding["code"] for finding in cleanup["findings"]})

    def test_renamed_files_are_left_to_the_regular_plan(self):
        projection = self.create(self.movies)
        self.apply(projection)
        MediaItem.objects.filter(pk=self.matrix.pk).update(title="Matrix")

        self.assertEqual(self.cleanup(projection)["total"], 0)
        self.assertEqual(self.folder.exists(), True)

    def test_changed_nfo_is_rewritten_and_kept_as_a_backup(self):
        projection = self.create(self.movies)
        self.apply(projection)
        nfo = self.folder / "The Matrix (1999).nfo"
        nfo.write_text("<movie><title>Edited</title></movie>", encoding="utf-8")

        # A regular run leaves it alone.
        self.assertEqual(self.plan(projection)["changes"], 0)

        cleanup = self.cleanup(projection)
        self.assertEqual(cleanup["paths"], {"The Matrix (1999)/The Matrix (1999).nfo": "update"})
        self.assertEqual(cleanup["overview"]["cleanup"]["changed"], 1)
        self.assertIn("Changed outside LibraryForge", cleanup["actions"]["results"][0]["reason"])
        run = self.apply(projection, cleanup=True)

        self.assertEqual(run["counts"], {"replaced": 1}, run)
        self.assertIn("<mpaa>R</mpaa>", nfo.read_text("utf-8"))
        backups = [path for path in self.folder.iterdir() if ".libraryforge-backup-" in path.name]
        self.assertEqual(len(backups), 1)
        self.assertTrue(backups[0].name.endswith(".nfo"))
        self.assertIn("Edited", backups[0].read_text("utf-8"))
        journal = self.client.get(f"/api/projection-runs/{run['id']}/actions/").data["results"]
        self.assertIn(backups[0].name, journal[0]["message"])
        self.assertEqual(self.cleanup(projection)["total"], 0)
        self.assertEqual(self.plan(projection)["changes"], 0)

    def test_unverified_legacy_files_are_left_alone(self):
        projection = self.create(self.movies)
        self.apply(projection)
        nfo = self.folder / "The Matrix (1999).nfo"
        nfo.write_text("<movie><title>Edited</title></movie>", encoding="utf-8")
        ProjectionFile.objects.filter(projection=projection).update(ownership=ProjectionFile.Ownership.LEGACY_UNVERIFIED)

        self.assertEqual(self.cleanup(projection)["total"], 0)

    def test_missing_files_are_written_again(self):
        projection = self.create(self.movies)
        self.apply(projection)
        (self.folder / "The Matrix (1999).mkv").unlink()
        (self.folder / "poster.jpg").unlink()

        cleanup = self.cleanup(projection)
        self.assertEqual(
            cleanup["paths"], {"The Matrix (1999)/The Matrix (1999).mkv": "relink", "The Matrix (1999)/poster.jpg": "update"}
        )
        run = self.apply(projection, cleanup=True)

        self.assertEqual(run["counts"], {"relinked": 1, "updated": 1}, run)
        self.assertTrue(os.path.samefile(self.folder / "The Matrix (1999).mkv", Path(self.movies.path, "matrix/the.matrix.1999.mkv")))
        self.assertTrue((self.folder / "poster.jpg").exists())

    def test_changed_videos_are_only_reported(self):
        projection = self.create(self.movies)
        self.apply(projection)
        video = self.folder / "The Matrix (1999).mkv"
        video.unlink()
        video.write_bytes(b"a different, longer video")

        cleanup = self.cleanup(projection)

        self.assertEqual(cleanup["total"], 0)
        self.assertIn("CHANGED_VIDEOS", {finding["code"] for finding in cleanup["findings"]})
        self.assertEqual(video.read_bytes(), b"a different, longer video")

    def test_overwrite_needs_a_reviewed_cleanup(self):
        projection = self.create(self.movies)
        self.apply(projection)
        nfo = self.folder / "The Matrix (1999).nfo"
        nfo.write_text("<movie><title>Edited</title></movie>", encoding="utf-8")
        MediaItem.objects.filter(pk=self.matrix.pk).update(content_rating="PG")

        run = self.apply(projection)

        self.assertEqual(run["counts"]["conflict"], 1, run)
        self.assertIn("Edited", nfo.read_text("utf-8"))

    def test_action_search(self):
        projection = self.create(self.movies)
        data = self.plan(projection)
        rows = self.client.get(f"/api/projection-plans/{data['id']}/actions/", {"q": "POSTER"}).data
        self.assertEqual([row["path"] for row in rows["results"]], ["The Matrix (1999)/poster.jpg"])


class InPlaceCleanupTests(_InPlace):
    def test_removes_a_kept_copy(self):
        art = self.art(self.movies, ArtworkFile.TargetType.MEDIA_ITEM, self.matrix.id, "matrix/folder.jpg", body=FOLDER_ART)
        projection = self.in_place(self.movies)
        Projection.objects.filter(pk=projection.pk).update(stale_policy="keep")
        self.apply(projection)
        ArtworkFile.objects.filter(id=art.id).update(is_selected=False)
        self.assertEqual(self.plan(projection)["paths"], {"matrix/poster.jpg": "retain"})

        cleanup = self.plan(projection, cleanup=True)

        self.assertEqual(cleanup["paths"], {"matrix/poster.jpg": "delete"})
        run = self.apply(projection, cleanup=True)
        self.assertEqual(run["counts"], {"deleted": 1}, run)
        self.assertFalse(self.disk(self.movies, "matrix/poster.jpg").exists())
        self.assertTrue(self.disk(self.movies, "matrix/folder.jpg").exists())

    def test_read_only_blocks_cleanup(self):
        projection = self.in_place(self.movies)
        Library.objects.filter(pk=self.movies.pk).update(management_mode=Library.ManagementMode.READ_ONLY)
        self.assertEqual(self.plan(projection, cleanup=True)["status"], "blocked")


class OverviewTests(_Movies):
    def test_lists_projections_roots_and_runs(self):
        projection = self.create(self.movies)
        run = self.apply(projection)
        self.plan(projection)
        in_place = self.client.post(f"/api/libraries/{self.movies.id}/projections/", {"layout": "library_nfo"}, format="json")
        self.assertEqual(in_place.status_code, 201, in_place.data)

        other = get_user_model().objects.create_user(email="other@example.com", password="password")
        other_library = Library.objects.create(owner=other, name="Theirs", path=str(self.tmp / "theirs"), content_type="movies")
        Projection.objects.create(
            library=other_library, output_profile=OutputProfile.objects.create(owner=other, name="J", target="jellyfin"),
            name="Theirs", destination_path=str(self.tmp / "out" / "theirs"), layout="movies",
        )

        roots = [str(self.tmp / "out"), str(self.tmp / "new"), str(self.tmp / "gone" / "new")]
        with override_settings(LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS=roots):
            data = self.client.get("/api/outputs/").data

        self.assertEqual(
            data["roots"],
            [
                {"path": roots[0], "state": "ready", "available": True, "projections": 1},
                {"path": roots[1], "state": "creatable", "available": False, "projections": 0},
                {"path": roots[2], "state": "missing", "available": False, "projections": 0},
            ],
        )
        rows = {row["layout"]: row for row in data["projections"]}
        self.assertEqual(set(rows), {"movies", "library_nfo"})
        folder = rows["movies"]
        self.assertEqual(folder["library_name"], "Movies")
        self.assertEqual(folder["target_label"], "Jellyfin")
        self.assertEqual(folder["managed_files"], 3)
        self.assertEqual(folder["latest_run"]["id"], run["id"])
        self.assertEqual(folder["latest_plan"]["status"], "ready")
        self.assertEqual(folder["latest_plan"]["changes"], 0)
        self.assertTrue(rows["library_nfo"]["in_place"])
        self.assertIsNone(rows["library_nfo"]["latest_plan"])
        self.assertEqual([item["id"] for item in data["recent_runs"]], [run["id"]])
        self.assertEqual(data["recent_runs"][0]["library_name"], "Movies")

        roots = self.client.get("/api/output-roots/").data["results"]
        self.assertEqual(roots, [{"path": str(self.tmp / "out"), "state": "ready", "available": True, "projections": 1}])

    def test_history_outlives_a_deleted_projection(self):
        projection = self.create(self.movies)
        run = self.apply(projection)
        self.assertEqual(self.client.delete(f"/api/projections/{projection.id}/").status_code, 204)

        self.assertEqual(self.client.get(f"/api/projection-runs/{run['id']}/").status_code, 200)
        runs = self.client.get("/api/outputs/").data["recent_runs"]
        self.assertEqual(runs[0]["id"], run["id"])
        self.assertEqual(runs[0]["projection_name"], projection.name)

        other = get_user_model().objects.create_user(email="other@example.com", password="password")
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get(f"/api/projection-runs/{run['id']}/").status_code, 404)
