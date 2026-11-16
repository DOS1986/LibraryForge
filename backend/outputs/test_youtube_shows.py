"""Channels as TV shows: hardlinked, renamed videos with NFOs, kept in sync."""

import errno
import os
import shutil
import tempfile
import uuid
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from catalog.models import ArtworkFile, Channel, OnlineVideo
from jobs.models import ScanJob
from libraries.models import Library
from media.models import MediaFile, MediaItem
from outputs.models import (
    Projection,
    ProjectionFile,
    ProjectionPlan,
    ProjectionRun,
    ProjectionRunAction,
)
from outputs.security import overlapping_projection
from outputs.services.engine import (
    claim_next_run,
    execute_run,
    recover_interrupted_runs,
    run_detail,
)
from outputs.services.youtube_shows import safe_segment

JPEG = b"\xff\xd8\xff\xe0fake-jpeg"


class SegmentTests(APITestCase):
    def test_names_are_safe_everywhere(self):
        self.assertEqual(safe_segment('Kids: "Best" Songs?', 60), "Kids_ _Best_ Songs_")
        self.assertEqual(safe_segment("CON", 60), "_CON")
        self.assertEqual(safe_segment("  ...  ", 60), "Untitled")
        self.assertEqual(safe_segment("a/b\\c", 60), "a_b_c")
        self.assertEqual(len(safe_segment("x" * 200, 80)), 80)


class _ShowsBase(APITestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.source = self.tmp / "Youtube"
        self.source.mkdir()
        self.dest = self.tmp / "YouTube Shows"
        settings_patch = override_settings(LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS=[str(self.tmp)])
        settings_patch.enable()
        self.addCleanup(settings_patch.disable)

        user_model = get_user_model()
        self.user = user_model.objects.create_user(email="owner@example.com", password="password")
        self.other = user_model.objects.create_user(email="other@example.com", password="password")
        self.client.force_authenticate(self.user)
        self.library = Library.objects.create(
            owner=self.user,
            name="Youtube",
            path=str(self.source),
            content_type="online_video",
            management_mode=Library.ManagementMode.SIDECAR_ONLY,
        )
        self.channel = Channel.objects.create(
            library=self.library,
            provider="youtube",
            source_id="UCkids",
            title="Kids Songs",
            description="Songs for kids.",
            content_rating="TV-Y",
        )
        self.first = self.video("vid1", "Wheels on the Bus", date(2024, 5, 12))
        self.second = self.video("vid2", "Baby Shark", date(2024, 5, 12))
        self.third = self.video("vid3", "ABC Song", date(2023, 1, 3))
        # Removals need a finished scan of the library.
        ScanJob.objects.create(library=self.library, status=ScanJob.Status.COMPLETED)

        thumb_patch = patch("outputs.services.youtube_shows._thumbnail", return_value=JPEG)
        art_patch = patch("outputs.services.youtube_shows._channel_artwork", return_value={})
        thumb_patch.start()
        self.artwork = art_patch.start()
        self.addCleanup(thumb_patch.stop)
        self.addCleanup(art_patch.stop)

    def video(self, source_id, title, upload, channel=None, *, body=None, thumb=False):
        channel = channel or self.channel
        relative = f"{channel.source_id}/{source_id}.mp4"
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        data = body or f"video {source_id}".encode()
        path.write_bytes(data)
        item = MediaItem.objects.create(
            library=self.library, title=title, description=f"About {title}", media_type=MediaItem.MediaType.ONLINE_VIDEO
        )
        media_file = MediaFile.objects.create(
            library=self.library,
            media_item=item,
            relative_path=relative,
            file_name=f"{source_id}.mp4",
            extension="mp4",
            size_bytes=len(data),
            duration_seconds=125,
            is_present=True,
        )
        OnlineVideo.objects.create(
            library=self.library, media_item=item, channel=channel, provider="youtube", source_id=source_id, upload_date=upload
        )
        if thumb:
            ArtworkFile.objects.create(
                library=self.library,
                target_type=ArtworkFile.TargetType.MEDIA_ITEM,
                target_id=item.id,
                artwork_type=ArtworkFile.ArtworkType.PRIMARY,
                source_name="embedded-cover",
                relative_path=f"@embedded/{media_file.id}/2.png",
                file_name="embedded-stream-2.png",
                extension="png",
                size_bytes=10,
                modified_ns=1,
                is_present=True,
            )
        return media_file

    def create(self, destination=None, *, acknowledge=True):
        response = self.client.post(
            f"/api/libraries/{self.library.id}/youtube-shows/",
            {"destination_path": str(destination or self.dest), "hardlink_acknowledged": acknowledge},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return Projection.objects.get(id=response.data["id"])

    def plan(self, projection, **body):
        response = self.client.post(f"/api/projections/{projection.id}/plans/", body, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        data = response.data
        data["paths"] = {row["path"] for row in data["actions"]["results"]}
        return data

    def request(self, plan, key=None):
        return self.client.post(
            f"/api/projection-plans/{plan['id']}/runs/",
            {"digest": plan["digest"], "idempotency_key": key or str(uuid.uuid4())},
            format="json",
        )

    def apply(self, plan):
        response = self.request(plan)
        self.assertEqual(response.status_code, 202, response.data)
        run = execute_run(ProjectionRun.objects.get(id=response.data["id"]))
        return run_detail(run)

    def sync_all(self, projection, **body):
        run = self.apply(self.plan(projection, **body))
        return run["counts"], run

    def episode(self, media_file, projection):
        return ProjectionFile.objects.get(projection=projection, media_file=media_file, kind="video")


class LayoutTests(_ShowsBase):
    def test_plan_lays_out_channels_as_shows(self):
        projection = self.create()
        data = self.plan(projection)

        self.assertEqual(data["status"], "ready")
        self.assertIn("Kids Songs/tvshow.nfo", data["paths"])
        self.assertIn("Kids Songs/Season 2024/S2024E051201 - Wheels on the Bus [vid1].mp4", data["paths"])
        self.assertIn("Kids Songs/Season 2024/S2024E051202 - Baby Shark [vid2].mp4", data["paths"])
        self.assertIn("Kids Songs/Season 2023/S2023E010301 - ABC Song [vid3].nfo", data["paths"])
        self.assertEqual(data["overview"]["files"]["video"], 3)
        self.assertEqual(data["overview"]["channels"][0]["folder"], "Kids Songs")
        # Planning never touches the disk.
        self.assertFalse(self.dest.exists())

    def test_run_hardlinks_and_writes_nfos(self):
        projection = self.create()
        counts, run = self.sync_all(projection)

        self.assertEqual(run["status"], "succeeded")
        self.assertEqual(counts["created"], 7)  # 3 videos, 3 episode NFOs, 1 tvshow.nfo
        video = self.dest / "Kids Songs/Season 2024/S2024E051201 - Wheels on the Bus [vid1].mp4"
        self.assertTrue(os.path.samefile(video, self.source / "UCkids/vid1.mp4"))
        nfo = (self.dest / "Kids Songs/Season 2024/S2024E051201 - Wheels on the Bus [vid1].nfo").read_text("utf-8")
        for expected in (
            "<episodedetails>",
            "<season>2024</season>",
            "<episode>51201</episode>",
            "<aired>2024-05-12</aired>",
            "<mpaa>TV-Y</mpaa>",
            "<runtime>2</runtime>",
            '<uniqueid type="youtube" default="true">vid1</uniqueid>',
        ):
            self.assertIn(expected, nfo)
        show = (self.dest / "Kids Songs/tvshow.nfo").read_text("utf-8")
        self.assertIn("<mpaa>TV-Y</mpaa>", show)
        self.assertIn("<premiered>2023-01-03</premiered>", show)
        # An unchanged rerun plans nothing.
        self.assertEqual(self.plan(projection)["changes"], 0)
        # TubeArchivist's folder is unchanged; every file is owned and journaled.
        self.assertEqual(sorted(p.name for p in (self.source / "UCkids").iterdir()), ["vid1.mp4", "vid2.mp4", "vid3.mp4"])
        self.assertFalse(ProjectionFile.objects.exclude(ownership=ProjectionFile.Ownership.OWNED).exists())
        self.assertEqual(ProjectionRunAction.objects.filter(state="done").count(), 7)
        projection.refresh_from_db()
        self.assertEqual(str(projection.last_successful_run_id), run["id"])

    def test_copies_when_the_projection_copies(self):
        projection = self.create()
        Projection.objects.filter(pk=projection.pk).update(link_mode=Projection.LinkMode.COPY)
        projection.refresh_from_db()
        self.sync_all(projection)
        video = self.dest / "Kids Songs/Season 2024/S2024E051201 - Wheels on the Bus [vid1].mp4"
        self.assertFalse(os.path.samefile(video, self.source / "UCkids/vid1.mp4"))
        self.assertEqual(video.read_bytes(), b"video vid1")
        self.assertEqual(self.plan(projection)["changes"], 0)

    def test_thumbnails_and_channel_artwork(self):
        self.video("vid4", "Colors", date(2024, 6, 1), thumb=True)
        self.artwork.return_value = {"poster": (JPEG, "jpg"), "fanart": (JPEG, "png")}
        with patch("outputs.services.youtube_shows._artwork_links", return_value=[object()]):
            projection = self.create()
            self.assertEqual(self.plan(projection)["counts"]["artwork"], 1)
            self.sync_all(projection)
            self.assertEqual(self.plan(projection)["changes"], 0)

        self.assertEqual((self.dest / "Kids Songs/Season 2024/S2024E060101 - Colors [vid4]-thumb.jpg").read_bytes(), JPEG)
        self.assertEqual((self.dest / "Kids Songs/poster.jpg").read_bytes(), JPEG)
        self.assertTrue((self.dest / "Kids Songs/fanart.png").exists())


class SyncTests(_ShowsBase):
    def setUp(self):
        super().setUp()
        self.projection = self.create()
        self.sync_all(self.projection)

    def test_rating_changes_reach_every_nfo(self):
        self.channel.content_rating = "TV-Y7"
        self.channel.save()

        self.assertEqual(self.plan(self.projection)["counts"]["update"], 4)
        self.sync_all(self.projection)
        self.assertIn("<mpaa>TV-Y7</mpaa>", (self.dest / "Kids Songs/tvshow.nfo").read_text("utf-8"))
        self.assertIn(
            "<mpaa>TV-Y7</mpaa>",
            (self.dest / "Kids Songs/Season 2023/S2023E010301 - ABC Song [vid3].nfo").read_text("utf-8"),
        )

    def test_renamed_title_moves_the_episode_and_keeps_its_number(self):
        item = self.second.media_item
        item.title = "Baby Shark Dance"
        item.save()

        counts, _run = self.sync_all(self.projection)

        season = self.dest / "Kids Songs/Season 2024"
        self.assertTrue((season / "S2024E051202 - Baby Shark Dance [vid2].mp4").exists())
        self.assertFalse((season / "S2024E051202 - Baby Shark [vid2].mp4").exists())
        self.assertFalse((season / "S2024E051202 - Baby Shark [vid2].nfo").exists())
        self.assertEqual(counts["deleted"], 2)
        self.assertEqual(self.episode(self.second, self.projection).episode_number, 51202)

    def test_new_same_day_video_never_renumbers_existing_ones(self):
        # "vid0" sorts before vid1 but arrived later: it gets the next number.
        late = self.video("vid0", "Late Upload", date(2024, 5, 12))
        self.sync_all(self.projection)
        self.assertEqual(self.episode(self.first, self.projection).episode_number, 51201)
        self.assertEqual(self.episode(late, self.projection).episode_number, 51203)

    def test_removed_video_is_unlinked_after_a_complete_scan(self):
        self.third.is_present = False
        self.third.save()

        counts, _run = self.sync_all(self.projection)

        self.assertEqual(counts["deleted"], 2)
        self.assertFalse((self.dest / "Kids Songs/Season 2023").exists())
        self.assertTrue((self.source / "UCkids/vid3.mp4").exists())

    def test_removals_wait_for_a_complete_scan(self):
        ScanJob.objects.filter(library=self.library).update(status=ScanJob.Status.FAILED)
        self.third.is_present = False
        self.third.save()

        data = self.plan(self.projection)

        self.assertEqual(data["counts"].get("retain"), 2)
        self.assertNotIn("delete", data["counts"])
        self.assertEqual(data["findings"][0]["code"], "STALE_KEPT")
        self.apply(data)
        self.assertTrue((self.dest / "Kids Songs/Season 2023").exists())

    def test_keep_policy_never_removes(self):
        Projection.objects.filter(pk=self.projection.pk).update(stale_policy=Projection.StalePolicy.KEEP)
        self.projection.refresh_from_db()
        self.third.is_present = False
        self.third.save()
        self.assertEqual(self.plan(self.projection)["counts"].get("retain"), 2)

    def test_files_changed_outside_are_left_alone(self):
        nfo = self.dest / "Kids Songs/tvshow.nfo"
        nfo.write_text("<tvshow><title>Edited by hand</title></tvshow>", encoding="utf-8")
        self.channel.content_rating = "TV-G"
        self.channel.save()

        counts, run = self.sync_all(self.projection)

        self.assertEqual(counts["conflict"], 1)
        self.assertIn("changed outside LibraryForge", run["problems"][0]["message"])
        self.assertIn("Edited by hand", nfo.read_text("utf-8"))

    def test_foreign_files_are_never_overwritten_or_adopted(self):
        foreign = self.dest / "Kids Songs/Season 2024/S2024E061501 - New [vid9].mp4"
        foreign.write_bytes(b"someone else's file")
        self.video("vid9", "New", date(2024, 6, 15))

        counts, _run = self.sync_all(self.projection)

        self.assertEqual(counts["conflict"], 1)
        self.assertEqual(foreign.read_bytes(), b"someone else's file")

    def test_unrelated_files_in_the_destination_are_kept(self):
        keep = self.dest / "Kids Songs/Season 2023/notes.txt"
        keep.write_text("mine", encoding="utf-8")
        self.third.is_present = False
        self.third.save()

        self.sync_all(self.projection)

        self.assertEqual(keep.read_text("utf-8"), "mine")

    def test_replaced_source_is_relinked(self):
        path = self.source / "UCkids/vid1.mp4"
        path.unlink()
        path.write_bytes(b"re-downloaded and longer")
        self.first.size_bytes = path.stat().st_size
        self.first.save()

        self.assertEqual(self.plan(self.projection)["counts"]["relink"], 1)
        self.sync_all(self.projection)
        linked = self.dest / "Kids Songs/Season 2024/S2024E051201 - Wheels on the Bus [vid1].mp4"
        self.assertTrue(os.path.samefile(linked, path))


class PlanAndRunTests(_ShowsBase):
    def test_hardlinks_need_acknowledgement(self):
        projection = self.create(acknowledge=False)
        data = self.plan(projection)
        self.assertEqual(data["status"], "blocked")
        self.assertEqual(data["findings"][0]["code"], "HARDLINK_NOT_ACKNOWLEDGED")
        self.assertEqual(self.request(data).status_code, 422)

    def test_read_only_library_cannot_hardlink(self):
        projection = self.create()
        self.library.management_mode = Library.ManagementMode.READ_ONLY
        self.library.save()
        data = self.plan(projection)
        self.assertIn("HARDLINK_READ_ONLY", {finding["code"] for finding in data["findings"]})
        self.assertFalse(self.dest.exists())

    def test_stale_plans_are_refused(self):
        projection = self.create()
        first = self.plan(projection)
        tampered = {**first, "digest": "0" * 64}
        self.assertEqual(self.request(tampered).status_code, 409)

        second = self.plan(projection)  # replaces the first
        self.assertEqual(self.request(first).status_code, 409)
        self.apply(second)
        third = self.plan(projection)
        ProjectionFile.objects.filter(projection=projection).first().delete()  # output changed since planning
        self.assertEqual(self.request(third).status_code, 409)

    def test_expired_plans_are_refused(self):
        projection = self.create()
        data = self.plan(projection)
        ProjectionPlan.objects.filter(id=data["id"]).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.request(data).status_code, 409)

    def test_idempotent_requests_and_one_active_run(self):
        projection = self.create()
        data = self.plan(projection)
        first = self.request(data, key="same-key")
        again = self.request(data, key="same-key")
        self.assertEqual(first.data["id"], again.data["id"])
        self.assertEqual(self.request(data, key="other-key").status_code, 409)

    def test_cancel_a_queued_run(self):
        projection = self.create()
        run_id = self.request(self.plan(projection)).data["id"]
        response = self.client.post(f"/api/projection-runs/{run_id}/cancel/")
        self.assertEqual(response.data["status"], "cancelled")
        self.assertIsNone(claim_next_run("worker-1"))

    def test_worker_claims_queued_runs(self):
        projection = self.create()
        run_id = self.request(self.plan(projection)).data["id"]
        claimed = claim_next_run("worker-1")
        self.assertEqual((str(claimed.id), claimed.status), (run_id, "running"))
        self.assertEqual(recover_interrupted_runs({"other-worker"}), 1)
        self.assertEqual(ProjectionRun.objects.get(id=run_id).status, "interrupted")

    def test_interrupted_files_are_adopted_only_from_the_journal(self):
        projection = self.create()
        target = self.dest / "Kids Songs/Season 2024/S2024E051201 - Wheels on the Bus [vid1].mp4"
        target.parent.mkdir(parents=True)
        os.link(self.source / "UCkids/vid1.mp4", target)

        counts, _run = self.sync_all(projection)
        self.assertEqual(counts["conflict"], 1)  # same file, but nothing proves we made it

        # A run that recorded intent for this path, then stopped.
        stopped = ProjectionRun.objects.create(projection=projection, idempotency_key="stopped", status="interrupted")
        ProjectionRunAction.objects.create(
            run=stopped, ordinal=0, action="create", kind="video", relative_path=target.relative_to(self.dest).as_posix()
        )
        counts, _run = self.sync_all(projection)
        self.assertEqual(counts["adopted"], 1)

    def test_legacy_files_are_verified_once(self):
        projection = self.create()
        self.sync_all(projection)
        ProjectionFile.objects.filter(projection=projection).update(ownership=ProjectionFile.Ownership.LEGACY_UNVERIFIED)
        nfo = self.dest / "Kids Songs/tvshow.nfo"
        nfo.write_text("<tvshow><title>Edited</title></tvshow>", encoding="utf-8")
        (self.dest / "Kids Songs/Season 2023/S2023E010301 - ABC Song [vid3].nfo").unlink()

        data = self.plan(projection)

        self.assertIn("LEGACY_UNVERIFIED", {finding["code"] for finding in data["findings"]})
        self.assertEqual(data["counts"], {"create": 1})  # the missing NFO comes back
        rows = ProjectionFile.objects.filter(projection=projection)
        self.assertEqual(rows.filter(ownership=ProjectionFile.Ownership.LEGACY_UNVERIFIED).count(), 1)
        self.assertEqual(rows.filter(ownership=ProjectionFile.Ownership.LEGACY_VERIFIED).count(), 5)

    def test_cross_volume_destination_stops_with_an_explanation(self):
        projection = self.create()
        with patch("outputs.services.youtube_shows.os.link", side_effect=OSError(errno.EXDEV, "cross-device")):
            _counts, run = self.sync_all(projection)
        self.assertEqual(run["status"], "failed")
        self.assertIn("same share and volume", run["error"])

    def test_one_channel_at_a_time(self):
        other = Channel.objects.create(library=self.library, provider="youtube", source_id="UCother", title="Other")
        self.video("oth1", "Other video", date(2024, 1, 1), channel=other)
        projection = self.create()

        self.sync_all(projection, channel=str(other.id))

        self.assertTrue((self.dest / "Other/tvshow.nfo").exists())
        self.assertFalse((self.dest / "Kids Songs").exists())
        channels = {row["title"]: row for row in self.plan(projection)["overview"]["channels"]}
        self.assertEqual(channels["Other"]["pending"], 0)
        self.assertGreater(channels["Kids Songs"]["pending"], 0)

    def test_history_lists_runs_and_journal(self):
        projection = self.create()
        _counts, run = self.sync_all(projection)
        history = self.client.get(f"/api/projections/{projection.id}/runs/").data
        self.assertEqual(history["results"][0]["id"], run["id"])
        self.assertEqual(history["managed_files"], 7)
        journal = self.client.get(f"/api/projection-runs/{run['id']}/actions/").data
        self.assertEqual(journal["total"], 7)


class GuardTests(_ShowsBase):
    def test_destination_inside_any_library_is_refused(self):
        response = self.client.post(
            f"/api/libraries/{self.library.id}/youtube-shows/",
            {"destination_path": str(self.source / "shows")},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        other_library = self.tmp / "Movies"
        other_library.mkdir()
        Library.objects.create(owner=self.other, name="Movies", path=str(other_library), content_type="movies")
        response = self.client.post(
            f"/api/libraries/{self.library.id}/youtube-shows/",
            {"destination_path": str(other_library / "shows")},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Movies", str(response.data))

    def test_an_output_root_is_always_required(self):
        with override_settings(LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS=[], DEBUG=True):
            response = self.client.post(
                f"/api/libraries/{self.library.id}/youtube-shows/", {"destination_path": str(self.dest)}, format="json"
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS", str(response.data))

    def test_output_folders_cannot_become_libraries(self):
        self.create()
        self.assertIsNotNone(overlapping_projection(self.dest / "Kids Songs"))
        self.assertIsNone(overlapping_projection(self.tmp / "Elsewhere"))

    def test_old_routes_are_gone(self):
        projection = self.create()
        for method, route in (("get", "shows-plan"), ("post", "shows-sync"), ("get", "preview"), ("post", "run")):
            self.assertEqual(getattr(self.client, method)(f"/api/projections/{projection.id}/{route}/").status_code, 404)

    def test_other_users_cannot_see_plans_or_runs(self):
        projection = self.create()
        data = self.plan(projection)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post(f"/api/projections/{projection.id}/plans/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/projection-plans/{data['id']}/").status_code, 404)
        self.assertEqual(self.request(data).status_code, 404)
        self.assertEqual(self.client.get(f"/api/libraries/{self.library.id}/youtube-shows/").status_code, 404)
