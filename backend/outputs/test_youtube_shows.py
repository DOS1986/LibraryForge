"""Channels as TV shows: hardlinked, renamed videos with NFOs, kept in sync."""

import errno
import os
import shutil
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from catalog.models import ArtworkFile, Channel, OnlineVideo
from libraries.models import Library
from media.models import MediaFile, MediaItem
from outputs.models import Projection, ProjectionFile
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

    def create(self, destination=None):
        response = self.client.post(
            f"/api/libraries/{self.library.id}/youtube-shows/",
            {"destination_path": str(destination or self.dest)},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return Projection.objects.get(id=response.data["id"])

    def plan(self, projection, **params):
        response = self.client.get(f"/api/projections/{projection.id}/shows-plan/", params)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def sync(self, projection, **body):
        response = self.client.post(f"/api/projections/{projection.id}/shows-sync/", body, format="json")
        return response

    def sync_all(self, projection, **body):
        totals = {}
        cursor = None
        while True:
            response = self.sync(projection, cursor=cursor, **body)
            self.assertEqual(response.status_code, 200, response.data)
            for key, value in response.data["counts"].items():
                totals[key] = totals.get(key, 0) + value
            cursor = response.data["next_cursor"]
            if not cursor:
                return totals, response.data

    def episode(self, media_file, projection):
        return ProjectionFile.objects.get(projection=projection, media_file=media_file, kind="video")


class LayoutTests(_ShowsBase):
    def test_plan_lays_out_channels_as_shows(self):
        projection = self.create()
        data = self.plan(projection)

        paths = {action["path"] for action in data["actions"]}
        self.assertIn("Kids Songs/tvshow.nfo", paths)
        self.assertIn("Kids Songs/Season 2024/S2024E051201 - Wheels on the Bus [vid1].mp4", paths)
        self.assertIn("Kids Songs/Season 2024/S2024E051202 - Baby Shark [vid2].mp4", paths)
        self.assertIn("Kids Songs/Season 2023/S2023E010301 - ABC Song [vid3].nfo", paths)
        self.assertEqual(data["files"]["video"], 3)
        self.assertEqual(data["channels"][0]["folder"], "Kids Songs")
        # Planning never touches the disk.
        self.assertFalse(self.dest.exists())

    def test_sync_hardlinks_and_writes_nfos(self):
        projection = self.create()
        totals, last = self.sync_all(projection, batch=3)

        self.assertEqual(totals["created"], 7)  # 3 videos, 3 episode NFOs, 1 tvshow.nfo
        self.assertIsNone(last["error"])
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
        self.assertEqual(self.plan(projection)["pending"], 0)
        # TubeArchivist's folder is unchanged.
        self.assertEqual(sorted(p.name for p in (self.source / "UCkids").iterdir()), ["vid1.mp4", "vid2.mp4", "vid3.mp4"])

    def test_thumbnails_and_channel_artwork(self):
        self.video("vid4", "Colors", date(2024, 6, 1), thumb=True)
        self.artwork.return_value = {"poster": (JPEG, "jpg"), "fanart": (JPEG, "png")}
        with patch("outputs.services.youtube_shows._artwork_links", return_value=[object()]):
            projection = self.create()
            self.assertEqual(self.plan(projection)["summary"]["artwork"], 1)
            self.sync_all(projection)
            self.assertEqual(self.plan(projection)["pending"], 0)

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

        data = self.plan(self.projection)
        self.assertEqual(data["summary"]["update"], 4)
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

        totals, _last = self.sync_all(self.projection)

        season = self.dest / "Kids Songs/Season 2024"
        self.assertTrue((season / "S2024E051202 - Baby Shark Dance [vid2].mp4").exists())
        self.assertFalse((season / "S2024E051202 - Baby Shark [vid2].mp4").exists())
        self.assertFalse((season / "S2024E051202 - Baby Shark [vid2].nfo").exists())
        self.assertEqual(totals["deleted"], 2)
        self.assertEqual(self.episode(self.second, self.projection).episode_number, 51202)

    def test_new_same_day_video_never_renumbers_existing_ones(self):
        # "vid0" sorts before vid1 but arrived later: it gets the next number.
        late = self.video("vid0", "Late Upload", date(2024, 5, 12))
        self.sync_all(self.projection)
        self.assertEqual(self.episode(self.first, self.projection).episode_number, 51201)
        self.assertEqual(self.episode(late, self.projection).episode_number, 51203)

    def test_removed_video_is_unlinked_and_empty_folders_removed(self):
        self.third.is_present = False
        self.third.save()

        totals, _last = self.sync_all(self.projection)

        self.assertEqual(totals["deleted"], 2)
        self.assertFalse((self.dest / "Kids Songs/Season 2023").exists())
        self.assertTrue((self.source / "UCkids/vid3.mp4").exists())

    def test_files_changed_outside_are_left_alone(self):
        nfo = self.dest / "Kids Songs/tvshow.nfo"
        nfo.write_text("<tvshow><title>Edited by hand</title></tvshow>", encoding="utf-8")
        self.channel.content_rating = "TV-G"
        self.channel.save()

        response = self.sync(self.projection, batch=200)

        self.assertEqual(response.data["counts"]["conflict"], 1)
        self.assertIn("changed outside LibraryForge", response.data["problems"][0]["message"])
        self.assertIn("Edited by hand", nfo.read_text("utf-8"))

    def test_foreign_files_are_never_overwritten(self):
        foreign = self.dest / "Kids Songs/Season 2024/S2024E061501 - New [vid9].mp4"
        foreign.write_bytes(b"someone else's file")
        self.video("vid9", "New", date(2024, 6, 15))

        response = self.sync(self.projection, batch=200)

        self.assertEqual(response.data["counts"]["conflict"], 1)
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

        data = self.plan(self.projection)
        self.assertEqual(data["summary"]["relink"], 1)
        self.sync_all(self.projection)
        linked = self.dest / "Kids Songs/Season 2024/S2024E051201 - Wheels on the Bus [vid1].mp4"
        self.assertTrue(os.path.samefile(linked, path))


class GuardTests(_ShowsBase):
    def test_destination_inside_the_library_is_refused(self):
        response = self.client.post(
            f"/api/libraries/{self.library.id}/youtube-shows/",
            {"destination_path": str(self.source / "shows")},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_cross_volume_destination_stops_with_an_explanation(self):
        projection = self.create()
        with patch("outputs.services.youtube_shows.os.link", side_effect=OSError(errno.EXDEV, "cross-device")):
            response = self.sync(projection, batch=200)

        self.assertEqual(response.status_code, 200)
        self.assertIn("same share and volume", response.data["error"])
        self.assertIsNone(response.data["next_cursor"])

    def test_one_channel_at_a_time(self):
        other = Channel.objects.create(library=self.library, provider="youtube", source_id="UCother", title="Other")
        self.video("oth1", "Other video", date(2024, 1, 1), channel=other)
        projection = self.create()

        self.sync_all(projection, channel=str(other.id))

        self.assertTrue((self.dest / "Other/tvshow.nfo").exists())
        self.assertFalse((self.dest / "Kids Songs").exists())
        channels = {row["title"]: row for row in self.plan(projection)["channels"]}
        self.assertEqual(channels["Other"]["pending"], 0)
        self.assertGreater(channels["Kids Songs"]["pending"], 0)

    def test_template_preview_and_run_refuse_this_layout(self):
        projection = self.create()
        self.assertEqual(self.client.get(f"/api/projections/{projection.id}/preview/").status_code, 400)
        self.assertEqual(self.client.post(f"/api/projections/{projection.id}/run/").status_code, 400)

    def test_other_users_cannot_see_or_sync(self):
        projection = self.create()
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f"/api/projections/{projection.id}/shows-plan/").status_code, 404)
        self.assertEqual(self.sync(projection).status_code, 404)
        self.assertEqual(self.client.get(f"/api/libraries/{self.library.id}/youtube-shows/").status_code, 404)

    def test_read_only_library_is_refused(self):
        projection = self.create()
        self.library.management_mode = Library.ManagementMode.READ_ONLY
        self.library.save()
        response = self.sync(projection)
        self.assertEqual(response.status_code, 409)
        self.assertIn("Read Only", response.data["detail"])
