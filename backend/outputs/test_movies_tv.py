"""Movie and TV projections (Jellyfin): layouts, NFOs, copied artwork, findings."""

import datetime
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from catalog.models import ArtworkFile, Episode, MediaVersion, Season, Series
from jobs.models import ScanJob
from libraries.models import Library
from media.models import MediaFile, MediaItem
from outputs.models import OutputProfile, Projection, ProjectionRun
from outputs.services.engine import execute_run, run_detail

POSTER = b"\xff\xd8\xff\xe0poster-v1"


class _Base(APITestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        settings_patch = override_settings(LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS=[str(self.tmp / "out")])
        settings_patch.enable()
        self.addCleanup(settings_patch.disable)
        (self.tmp / "out").mkdir()
        user_model = get_user_model()
        self.user = user_model.objects.create_user(email="owner@example.com", password="password")
        self.client.force_authenticate(self.user)

    def library(self, name, content_type):
        path = self.tmp / name
        path.mkdir()
        library = Library.objects.create(
            owner=self.user, name=name, path=str(path), content_type=content_type,
            management_mode=Library.ManagementMode.SIDECAR_ONLY,
        )
        ScanJob.objects.create(library=library, status=ScanJob.Status.COMPLETED)
        return library

    def file(self, library, item, relative, body=b"video"):
        path = Path(library.path, *relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        media_file = MediaFile.objects.create(
            library=library, media_item=item, relative_path=relative, file_name=path.name, extension=path.suffix[1:],
            size_bytes=len(body), duration_seconds=5400, is_present=True,
        )
        MediaVersion.objects.create(media_item=item, media_file=media_file, name="main", is_primary=True)
        return media_file

    def art(self, library, target_type, target_id, relative, artwork_type=ArtworkFile.ArtworkType.PRIMARY, body=POSTER):
        path = Path(library.path, *relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        stat = path.stat()
        return ArtworkFile.objects.create(
            library=library, target_type=target_type, target_id=target_id, artwork_type=artwork_type,
            source_name="poster", relative_path=relative, file_name=path.name, extension=path.suffix[1:],
            size_bytes=stat.st_size, modified_ns=stat.st_mtime_ns, is_selected=True, is_present=True,
        )

    def create(self, library, name="out", **body):
        response = self.client.post(
            f"/api/libraries/{library.id}/projections/",
            {"destination_path": str(self.tmp / "out" / name), "hardlink_acknowledged": True, **body},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return Projection.objects.get(id=response.data["id"])

    def plan(self, projection, **body):
        response = self.client.post(f"/api/projections/{projection.id}/plans/", body, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        data = response.data
        actions = self.client.get(f"/api/projection-plans/{data['id']}/actions/", {"page_size": 500}).data
        data["paths"] = {row["path"]: row["action"] for row in actions["results"]}
        return data

    def apply(self, projection, **body):
        data = self.plan(projection, **body)
        response = self.client.post(
            f"/api/projection-plans/{data['id']}/runs/",
            {"digest": data["digest"], "idempotency_key": str(uuid.uuid4())},
            format="json",
        )
        self.assertEqual(response.status_code, 202, response.data)
        return run_detail(execute_run(ProjectionRun.objects.get(id=response.data["id"])))


class MovieTests(_Base):
    def setUp(self):
        super().setUp()
        self.movies = self.library("Movies", "movies")
        self.matrix = MediaItem.objects.create(
            library=self.movies, title="The Matrix", media_type=MediaItem.MediaType.MOVIE, content_rating="R",
            description="Neo wakes up.", genres=["Sci-Fi"], release_date=datetime.date(1999, 3, 31),
            external_ids={"imdb": "tt0133093", "tmdb": "603"},
        )
        self.matrix_file = self.file(self.movies, self.matrix, "matrix/the.matrix.1999.mkv")
        self.poster = self.art(self.movies, ArtworkFile.TargetType.MEDIA_ITEM, self.matrix.id, "matrix/poster.jpg")
        self.dest = self.tmp / "out" / "out"

    def test_layout_nfo_and_artwork(self):
        projection = self.create(self.movies)
        data = self.plan(projection)
        self.assertEqual(
            set(data["paths"]),
            {"The Matrix (1999)/The Matrix (1999).mkv", "The Matrix (1999)/The Matrix (1999).nfo", "The Matrix (1999)/poster.jpg"},
        )
        self.assertEqual(projection.layout, "movies")

        run = self.apply(projection)

        self.assertEqual(run["status"], "succeeded", run)
        folder = self.dest / "The Matrix (1999)"
        self.assertTrue(os.path.samefile(folder / "The Matrix (1999).mkv", Path(self.movies.path, "matrix/the.matrix.1999.mkv")))
        nfo = (folder / "The Matrix (1999).nfo").read_text("utf-8")
        for expected in ("<movie>", "<title>The Matrix</title>", "<year>1999</year>", "<mpaa>R</mpaa>", "<runtime>90</runtime>",
                         '<uniqueid type="imdb" default="true">tt0133093</uniqueid>', '<uniqueid type="tmdb">603</uniqueid>'):
            self.assertIn(expected, nfo)
        self.assertEqual((folder / "poster.jpg").read_bytes(), POSTER)
        self.assertFalse(os.path.samefile(folder / "poster.jpg", Path(self.movies.path, "matrix/poster.jpg")))  # copied
        self.assertEqual(self.plan(projection)["changes"], 0)

    def test_changed_artwork_and_rating_are_updated(self):
        projection = self.create(self.movies)
        self.apply(projection)
        Path(self.movies.path, "matrix/poster.jpg").write_bytes(b"\xff\xd8\xff\xe0poster-v2-bigger")
        stat = Path(self.movies.path, "matrix/poster.jpg").stat()
        ArtworkFile.objects.filter(pk=self.poster.pk).update(size_bytes=stat.st_size, modified_ns=stat.st_mtime_ns)
        MediaItem.objects.filter(pk=self.matrix.pk).update(content_rating="PG-13")

        data = self.plan(projection)
        self.assertEqual(data["counts"], {"update": 2})
        self.apply(projection)
        folder = self.dest / "The Matrix (1999)"
        self.assertEqual((folder / "poster.jpg").read_bytes(), b"\xff\xd8\xff\xe0poster-v2-bigger")
        self.assertIn("<mpaa>PG-13</mpaa>", (folder / "The Matrix (1999).nfo").read_text("utf-8"))

    def test_same_title_and_year_get_stable_suffixes(self):
        remake = MediaItem.objects.create(
            library=self.movies, title="The Matrix", media_type=MediaItem.MediaType.MOVIE,
            release_date=datetime.date(1999, 1, 1),
        )
        self.file(self.movies, remake, "other/matrix.mkv")
        data = self.plan(self.create(self.movies))
        self.assertIn("The Matrix (1999) [imdb-tt0133093]/The Matrix (1999) [imdb-tt0133093].mkv", data["paths"])
        self.assertIn(f"The Matrix (1999) [{str(remake.id)[:8]}]/The Matrix (1999) [{str(remake.id)[:8]}].mkv", data["paths"])

    def test_movies_without_files_are_reported(self):
        MediaItem.objects.create(library=self.movies, title="Lost", media_type=MediaItem.MediaType.MOVIE)
        data = self.plan(self.create(self.movies))
        self.assertIn("NO_FILE", {finding["code"] for finding in data["findings"]})
        self.assertEqual(data["overview"]["movies"], 1)

    def test_foreign_files_and_drift_survive(self):
        projection = self.create(self.movies)
        folder = self.dest / "The Matrix (1999)"
        folder.mkdir(parents=True)
        (folder / "poster.jpg").write_bytes(b"someone else's poster")
        run = self.apply(projection)
        self.assertEqual(run["counts"]["conflict"], 1)
        self.assertEqual((folder / "poster.jpg").read_bytes(), b"someone else's poster")

        (folder / "The Matrix (1999).nfo").write_text("<movie><title>Edited</title></movie>", encoding="utf-8")
        MediaItem.objects.filter(pk=self.matrix.pk).update(content_rating="PG")
        run = self.apply(projection)
        self.assertGreaterEqual(run["counts"]["conflict"], 1)
        self.assertIn("Edited", (folder / "The Matrix (1999).nfo").read_text("utf-8"))

    def test_removed_movie_is_unlinked(self):
        projection = self.create(self.movies)
        self.apply(projection)
        MediaFile.objects.filter(pk=self.matrix_file.pk).update(is_present=False)
        run = self.apply(projection)
        self.assertEqual(run["counts"]["deleted"], 3)
        self.assertFalse((self.dest / "The Matrix (1999)").exists())
        self.assertTrue(Path(self.movies.path, "matrix/the.matrix.1999.mkv").exists())

    def test_overlong_paths_are_skipped(self):
        with patch("outputs.services.movies_tv.MAX_PATH", len(str(self.dest)) + 30):
            data = self.plan(self.create(self.movies))
        self.assertIn("PATH_TOO_LONG", {finding["code"] for finding in data["findings"]})

    def test_other_profiles_wait_for_phase_three(self):
        kodi = OutputProfile.objects.create(owner=self.user, name="Kodi", target=OutputProfile.Target.KODI)
        data = self.plan(self.create(self.movies, output_profile=str(kodi.id)))
        self.assertEqual(data["status"], "blocked")
        self.assertEqual(data["findings"][0]["code"], "PROFILE_NOT_SUPPORTED")


class TvTests(_Base):
    def setUp(self):
        super().setUp()
        self.tv = self.library("TV", "tv")
        self.bluey = Series.objects.create(
            library=self.tv, title="Bluey", semantic_key="bluey", start_year=2018, content_rating="TV-Y",
            external_ids={"tvdb": "353546"},
        )
        self.season = Season.objects.create(series=self.bluey, season_number=1, title="Season 1")
        self.first = self.episode(1, "Magic Xylophone")
        self.second = self.episode(2, "Hospital")
        self.art(self.tv, ArtworkFile.TargetType.SERIES, self.bluey.id, "Bluey/poster.jpg")
        self.art(self.tv, ArtworkFile.TargetType.SEASON, self.season.id, "Bluey/Season 1/folder.jpg")
        self.art(self.tv, ArtworkFile.TargetType.EPISODE, self.first.id, "Bluey/Season 1/e01-thumb.jpg", ArtworkFile.ArtworkType.PRIMARY)
        self.dest = self.tmp / "out" / "out"

    def episode(self, number, title, season=None, end=None):
        season = season or self.season
        item = MediaItem.objects.create(library=self.tv, title=title, media_type=MediaItem.MediaType.TV_EPISODE)
        episode = Episode.objects.create(
            media_item=item, season=season, episode_number=number, episode_end_number=end,
            air_date=datetime.date(2018, 10, number),
        )
        self.file(self.tv, item, f"{season.series.title}/Season {season.season_number}/e{number:02d}-{uuid.uuid4().hex[:4]}.mkv")
        return episode

    def test_layout_nfos_and_artwork(self):
        projection = self.create(self.tv)
        data = self.plan(projection)
        expected = {
            "Bluey (2018)/tvshow.nfo",
            "Bluey (2018)/poster.jpg",
            "Bluey (2018)/Season 01/poster.jpg",
            "Bluey (2018)/Season 01/Bluey S01E01 - Magic Xylophone.mkv",
            "Bluey (2018)/Season 01/Bluey S01E01 - Magic Xylophone.nfo",
            "Bluey (2018)/Season 01/Bluey S01E01 - Magic Xylophone-thumb.jpg",
            "Bluey (2018)/Season 01/Bluey S01E02 - Hospital.mkv",
            "Bluey (2018)/Season 01/Bluey S01E02 - Hospital.nfo",
        }
        self.assertEqual(set(data["paths"]), expected)
        self.assertEqual(data["overview"]["series"][0]["episodes"], 2)

        run = self.apply(projection)

        self.assertEqual(run["status"], "succeeded", run)
        season = self.dest / "Bluey (2018)/Season 01"
        nfo = (season / "Bluey S01E01 - Magic Xylophone.nfo").read_text("utf-8")
        for expected_tag in ("<episodedetails>", "<showtitle>Bluey</showtitle>", "<season>1</season>", "<episode>1</episode>",
                             "<aired>2018-10-01</aired>", "<mpaa>TV-Y</mpaa>"):
            self.assertIn(expected_tag, nfo)
        show = (self.dest / "Bluey (2018)/tvshow.nfo").read_text("utf-8")
        self.assertIn('<uniqueid type="tvdb" default="true">353546</uniqueid>', show)
        self.assertEqual(self.plan(projection)["changes"], 0)

    def test_multi_episode_files_are_skipped(self):
        # (Duplicate episode numbers can't exist: the catalog enforces one per season.)
        self.episode(3, "Double", end=4)
        data = self.plan(self.create(self.tv))
        self.assertIn("MULTI_EPISODE", {finding["code"] for finding in data["findings"]})
        self.assertFalse(any("S01E03" in path for path in data["paths"]))

    def test_one_series_at_a_time(self):
        other = Series.objects.create(library=self.tv, title="Other", semantic_key="other")
        other_season = Season.objects.create(series=other, season_number=1, title="Season 1")
        self.episode(1, "Pilot", season=other_season)
        projection = self.create(self.tv)

        data = self.plan(projection, channel=str(other.id))

        self.assertTrue(all(path.startswith("Other/") for path in data["paths"]))
        self.apply(projection, channel=str(other.id))
        self.assertTrue((self.dest / "Other/tvshow.nfo").exists())
        self.assertFalse((self.dest / "Bluey (2018)").exists())


class CreateTests(_Base):
    def test_layout_follows_content_type(self):
        movies = self.library("Movies", "movies")
        self.assertEqual(self.create(movies, name="m").layout, "movies")
        mixed = self.library("Mixed", "mixed")
        response = self.client.post(
            f"/api/libraries/{mixed.id}/projections/", {"destination_path": str(self.tmp / "out" / "x")}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.create(mixed, name="t", layout="tv").layout, "tv")

    def test_one_projection_per_folder(self):
        movies = self.library("Movies", "movies")
        self.create(movies, name="same")
        response = self.client.post(
            f"/api/libraries/{movies.id}/projections/", {"destination_path": str(self.tmp / "out" / "same")}, format="json"
        )
        self.assertEqual(response.status_code, 400)
