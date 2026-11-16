"""NFOs and artwork written into the library itself (in-place NFO output)."""

import datetime
import uuid
from pathlib import Path

from catalog.models import ArtworkFile, Episode, Season, Series
from libraries.models import Library
from media.models import MediaItem
from metadata.models import NfoFile
from outputs.models import OutputProfile, ProjectionPlan, ProjectionRun
from outputs.services.engine import execute_run, run_detail
from outputs.test_movies_tv import _Base

FOLDER_ART = b"\xff\xd8\xff\xe0folder-art"
OTHER_ART = b"\xff\xd8\xff\xe0someone-elses-poster"
EXISTING_NFO = (
    '<?xml version="1.0" encoding="utf-8"?>\r\n'
    "<movie>\r\n"
    "  <!-- written by hand -->\r\n"
    "  <title>The Matrix</title>\r\n"
    "  <mpaa>PG</mpaa>\r\n"
    "  <custom>keep me</custom>\r\n"
    "  <plot>Only the NFO knows this.</plot>\r\n"
    "</movie>\r\n"
)


class _InPlace(_Base):
    def setUp(self):
        super().setUp()
        self.movies = self.library("Movies", "movies")
        self.matrix = MediaItem.objects.create(
            library=self.movies, title="The Matrix", media_type=MediaItem.MediaType.MOVIE, content_rating="R",
            release_date=datetime.date(1999, 3, 31),
        )
        self.file(self.movies, self.matrix, "matrix/the.matrix.1999.mkv")

    def in_place(self, library, **body):
        response = self.client.post(f"/api/libraries/{library.id}/projections/", {"layout": "library_nfo", **body}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        from outputs.models import Projection

        return Projection.objects.get(id=response.data["id"])

    def disk(self, library, relative):
        return Path(library.path, *relative.split("/"))

    def index_nfo(self, library, item, relative, text):
        self.disk(library, relative).write_bytes(text.encode("utf-8"))
        return NfoFile.objects.create(
            library=library, media_item=item, relative_path=relative, file_name=Path(relative).name, raw_xml=text,
            parse_status=NfoFile.ParseStatus.OK, root_element="movie", is_present=True,
        )

    def run_plan(self, data):
        response = self.client.post(
            f"/api/projection-plans/{data['id']}/runs/",
            {"digest": data["digest"], "idempotency_key": str(uuid.uuid4())},
            format="json",
        )
        self.assertEqual(response.status_code, 202, response.data)
        return run_detail(execute_run(ProjectionRun.objects.get(id=response.data["id"])))


class MovieInPlaceTests(_InPlace):
    def test_creates_nfo_and_copies_art_then_reruns_clean(self):
        self.art(self.movies, ArtworkFile.TargetType.MEDIA_ITEM, self.matrix.id, "matrix/folder.jpg", body=FOLDER_ART)
        projection = self.in_place(self.movies)
        self.assertEqual(projection.destination_path, "")

        data = self.plan(projection)

        self.assertEqual(data["status"], "ready", data["findings"])
        self.assertEqual(data["paths"], {"matrix/the.matrix.1999.nfo": "create", "matrix/poster.jpg": "create"})
        run = self.apply(projection)
        self.assertEqual(run["status"], "succeeded", run)
        nfo = self.disk(self.movies, "matrix/the.matrix.1999.nfo").read_text("utf-8")
        self.assertIn("<mpaa>R</mpaa>", nfo)
        self.assertTrue(NfoFile.objects.filter(library=self.movies, media_item=self.matrix, is_present=True).exists())
        self.assertEqual(self.disk(self.movies, "matrix/poster.jpg").read_bytes(), FOLDER_ART)
        self.assertEqual(self.disk(self.movies, "matrix/folder.jpg").read_bytes(), FOLDER_ART)  # source untouched

        again = self.plan(projection)
        self.assertEqual(again["changes"], 0, again["paths"])
        self.assertEqual(self.apply(projection)["counts"], {})

    def test_updates_only_changed_fields_and_keeps_everything_else(self):
        self.index_nfo(self.movies, self.matrix, "matrix/the.matrix.1999.nfo", EXISTING_NFO)
        projection = self.in_place(self.movies)

        data = self.plan(projection)

        self.assertEqual(data["paths"], {"matrix/the.matrix.1999.nfo": "update"})
        self.assertIn("rating", data["actions"]["results"][0]["reason"])
        self.apply(projection)
        text = self.disk(self.movies, "matrix/the.matrix.1999.nfo").read_bytes().decode("utf-8")
        self.assertEqual(
            text,
            EXISTING_NFO.replace("<mpaa>PG</mpaa>", "<mpaa>R</mpaa>").replace(
                "  <custom>keep me</custom>\r\n",
                "  <custom>keep me</custom>\r\n",
            ).replace("</movie>", "  <premiered>1999-03-31</premiered>\r\n  <year>1999</year>\r\n</movie>"),
        )
        self.assertIn("<plot>Only the NFO knows this.</plot>", text)  # an NFO-only value is never erased
        self.assertEqual(self.plan(projection)["changes"], 0)

    def test_nfo_edited_after_planning_is_left_alone(self):
        self.index_nfo(self.movies, self.matrix, "matrix/the.matrix.1999.nfo", EXISTING_NFO)
        projection = self.in_place(self.movies)
        data = self.plan(projection)
        nfo_path = self.disk(self.movies, "matrix/the.matrix.1999.nfo")
        nfo_path.write_bytes(EXISTING_NFO.replace("keep me", "edited").encode("utf-8"))

        run = self.run_plan(data)

        self.assertEqual(run["counts"], {"conflict": 1})
        self.assertIn("edited", nfo_path.read_text("utf-8"))
        # The next plan doesn't touch it until the library is rescanned.
        self.assertIn("CHANGED_ON_DISK", {finding["code"] for finding in self.plan(projection)["findings"]})

    def test_read_only_library_is_refused(self):
        projection = self.in_place(self.movies)
        ready = self.plan(projection)
        self.assertEqual(ready["status"], "ready")

        Library.objects.filter(pk=self.movies.pk).update(management_mode=Library.ManagementMode.READ_ONLY)

        response = self.client.post(
            f"/api/projection-plans/{ready['id']}/runs/",
            {"digest": ready["digest"], "idempotency_key": str(uuid.uuid4())},
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        blocked = self.plan(projection)
        self.assertEqual(blocked["status"], "blocked")
        self.assertIn("LIBRARY_READ_ONLY", {finding["code"] for finding in blocked["findings"]})
        self.assertFalse(self.disk(self.movies, "matrix/the.matrix.1999.nfo").exists())

    def test_a_different_image_is_kept_as_a_backup(self):
        self.art(self.movies, ArtworkFile.TargetType.MEDIA_ITEM, self.matrix.id, "matrix/folder.jpg", body=FOLDER_ART)
        self.disk(self.movies, "matrix/poster.jpg").write_bytes(OTHER_ART)
        projection = self.in_place(self.movies)

        data = self.plan(projection)

        self.assertEqual(data["paths"]["matrix/poster.jpg"], "replace")
        run = self.apply(projection)
        self.assertEqual(run["counts"], {"created": 1, "replaced": 1}, run)
        self.assertEqual(self.disk(self.movies, "matrix/poster.jpg").read_bytes(), FOLDER_ART)
        backups = list(Path(self.movies.path, "matrix").glob("poster.libraryforge-backup-*.jpg"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), OTHER_ART)
        self.assertEqual(self.plan(projection)["changes"], 0)

    def test_an_image_already_in_place_is_left_alone(self):
        self.art(self.movies, ArtworkFile.TargetType.MEDIA_ITEM, self.matrix.id, "matrix/poster.jpg", body=FOLDER_ART)
        data = self.plan(self.in_place(self.movies))
        self.assertNotIn("matrix/poster.jpg", data["paths"])

    def test_deselected_copy_is_removed_but_edited_copy_survives(self):
        art = self.art(self.movies, ArtworkFile.TargetType.MEDIA_ITEM, self.matrix.id, "matrix/folder.jpg", body=FOLDER_ART)
        banner = self.art(
            self.movies, ArtworkFile.TargetType.MEDIA_ITEM, self.matrix.id, "matrix/b.jpg", ArtworkFile.ArtworkType.BANNER,
        )
        projection = self.in_place(self.movies)
        self.apply(projection)
        self.disk(self.movies, "matrix/banner.jpg").write_bytes(b"\xff\xd8\xff\xe0edited by hand")
        ArtworkFile.objects.filter(id__in=[art.id, banner.id]).update(is_selected=False)

        data = self.plan(projection)

        self.assertEqual(data["paths"], {"matrix/poster.jpg": "delete", "matrix/banner.jpg": "delete"})
        run = self.apply(projection)
        self.assertEqual(run["counts"], {"deleted": 1, "kept": 1}, run)
        self.assertFalse(self.disk(self.movies, "matrix/poster.jpg").exists())
        self.assertTrue(self.disk(self.movies, "matrix/banner.jpg").exists())
        self.assertTrue(self.disk(self.movies, "matrix/folder.jpg").exists())

    def test_shared_folders_get_art_only_under_kodi_names(self):
        other = MediaItem.objects.create(library=self.movies, title="Other", media_type=MediaItem.MediaType.MOVIE)
        self.file(self.movies, other, "matrix/other.mkv")
        self.art(self.movies, ArtworkFile.TargetType.MEDIA_ITEM, self.matrix.id, "matrix/art/matrix.jpg", body=FOLDER_ART)

        jellyfin = self.plan(self.in_place(self.movies))
        self.assertIn("SHARED_FOLDER", {finding["code"] for finding in jellyfin["findings"]})
        self.assertFalse(any(path.endswith(".jpg") for path in jellyfin["paths"]))

        kodi = OutputProfile.objects.create(owner=self.user, name="Kodi", target="kodi")
        projection = jellyfin_projection = self.movies.projections.get()
        response = self.client.patch(f"/api/projections/{jellyfin_projection.id}/", {"output_profile": str(kodi.id)}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("matrix/the.matrix.1999-poster.jpg", self.plan(projection)["paths"])

    def test_one_per_library_and_not_for_online_video(self):
        self.in_place(self.movies)
        response = self.client.post(f"/api/libraries/{self.movies.id}/projections/", {"layout": "library_nfo"}, format="json")
        self.assertEqual(response.status_code, 400)
        videos = self.library("Videos", "online_video")
        response = self.client.post(f"/api/libraries/{videos.id}/projections/", {"layout": "library_nfo"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_library_folder_stays_editable(self):
        from outputs.security import overlapping_projection

        self.in_place(self.movies)
        # In-place output has no folder of its own, so it never blocks a library path.
        self.assertIsNone(overlapping_projection(Path(self.movies.path).resolve()))
        self.assertIsNone(overlapping_projection(Path.cwd().resolve()))

    def test_changed_plan_input_supersedes(self):
        projection = self.in_place(self.movies)
        data = self.plan(projection)
        kodi = OutputProfile.objects.create(owner=self.user, name="Kodi", target="kodi")
        self.client.patch(f"/api/projections/{projection.id}/", {"output_profile": str(kodi.id)}, format="json")
        self.assertEqual(ProjectionPlan.objects.get(id=data["id"]).status, "superseded")


class TvInPlaceTests(_InPlace):
    def setUp(self):
        super().setUp()
        self.tv = self.library("TV", "tv")
        self.bluey = Series.objects.create(library=self.tv, title="Bluey", semantic_key="bluey", content_rating="TV-Y")
        self.season = Season.objects.create(series=self.bluey, season_number=1, title="Season 1")
        item = MediaItem.objects.create(library=self.tv, title="Magic Xylophone", media_type=MediaItem.MediaType.TV_EPISODE)
        self.first = Episode.objects.create(media_item=item, season=self.season, episode_number=1, air_date=datetime.date(2018, 10, 1))
        self.file(self.tv, item, "Bluey/Season 1/Bluey S01E01.mkv")
        self.art(self.tv, ArtworkFile.TargetType.SERIES, self.bluey.id, "Bluey/folder.jpg", body=FOLDER_ART)
        self.art(self.tv, ArtworkFile.TargetType.SEASON, self.season.id, "Bluey/Season 1/folder.jpg", body=FOLDER_ART)
        self.art(self.tv, ArtworkFile.TargetType.EPISODE, self.first.id, "Bluey/Season 1/still.jpg", ArtworkFile.ArtworkType.THUMB)

    def test_jellyfin_layout(self):
        projection = self.in_place(self.tv)
        data = self.plan(projection)
        self.assertEqual(
            data["paths"],
            {
                "Bluey/tvshow.nfo": "create",
                "Bluey/poster.jpg": "create",
                "Bluey/Season 1/poster.jpg": "create",
                "Bluey/Season 1/Bluey S01E01.nfo": "create",
                "Bluey/Season 1/Bluey S01E01-thumb.jpg": "create",
            },
        )
        self.apply(projection)
        self.assertIn("<mpaa>TV-Y</mpaa>", self.disk(self.tv, "Bluey/tvshow.nfo").read_text("utf-8"))
        self.assertEqual(self.plan(projection)["changes"], 0)

    def test_kodi_season_art_goes_in_the_show_folder(self):
        projection = self.in_place(self.tv, target="kodi")
        paths = self.plan(projection)["paths"]
        self.assertIn("Bluey/season01-poster.jpg", paths)
        self.assertNotIn("Bluey/Season 1/poster.jpg", paths)
