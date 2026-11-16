"""Writing catalog ratings into existing NFO files (real files in a temp dir)."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APIClient, APITestCase

from catalog.models import Episode, Season, Series
from libraries.models import Library
from media.models import MediaFile, MediaItem
from metadata.models import NfoFile
from metadata.services import secure_nfo
from metadata.services.nfo_rating_export import set_mpaa

MOVIE_NFO = """<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<movie>
  <!-- written by another tool -->
  <title>Cars</title>
  <mpaa>NR</mpaa>
  <plot>Fast &amp; loud.</plot>
</movie>
"""

NO_MPAA_NFO = "<tvshow>\r\n\t<title>Bluey</title>\r\n\t<year>2018</year>\r\n</tvshow>\r\n"


class SetMpaaTests(SimpleTestCase):
    def test_replaces_value_and_keeps_everything_else(self):
        updated = set_mpaa(MOVIE_NFO, "movie", "G")
        self.assertEqual(updated, MOVIE_NFO.replace("<mpaa>NR</mpaa>", "<mpaa>G</mpaa>"))

    def test_adds_missing_tag_with_file_indentation_and_line_endings(self):
        updated = set_mpaa(NO_MPAA_NFO, "tvshow", "TV-Y")
        self.assertEqual(
            updated,
            "<tvshow>\r\n\t<title>Bluey</title>\r\n\t<year>2018</year>\r\n\t<mpaa>TV-Y</mpaa>\r\n</tvshow>\r\n",
        )

    def test_inline_and_empty_forms(self):
        self.assertEqual(set_mpaa("<movie><title>X</title></movie>", "movie", "PG"), "<movie><title>X</title><mpaa>PG</mpaa></movie>")
        self.assertEqual(set_mpaa("<movie><mpaa/></movie>", "movie", "PG"), "<movie><mpaa>PG</mpaa></movie>")
        self.assertEqual(set_mpaa("<movie><mpaa></mpaa></movie>", "movie", "PG"), "<movie><mpaa>PG</mpaa></movie>")

    def test_value_is_escaped(self):
        self.assertIn("<mpaa>A&amp;B &lt;x&gt;</mpaa>", set_mpaa("<movie></movie>", "movie", "A&B <x>"))

    def test_requires_closing_root(self):
        with self.assertRaises(ValueError):
            set_mpaa("<movie><title>X</title>", "movie", "PG")


class _ExportTestCase(APITestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        user_model = get_user_model()
        self.user = user_model.objects.create_user(email="owner@example.com", password="password")
        self.other = user_model.objects.create_user(email="other@example.com", password="password")
        self.client.force_authenticate(self.user)
        self.library = Library.objects.create(
            owner=self.user,
            name="Movies",
            path=str(self.root / "movies"),
            content_type="movies",
            management_mode=Library.ManagementMode.SIDECAR_ONLY,
        )
        self.tv = Library.objects.create(
            owner=self.user,
            name="TV",
            path=str(self.root / "tv"),
            content_type="tv",
            management_mode=Library.ManagementMode.SIDECAR_ONLY,
        )

    def write_nfo(self, library, relative, content, item=None, media_file=None):
        path = Path(library.path, *relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))
        stat = path.stat()
        parsed = secure_nfo.parse_nfo_content(content)
        return NfoFile.objects.create(
            library=library,
            media_item=item,
            media_file=media_file,
            relative_path=relative,
            file_name=relative.rsplit("/", 1)[-1],
            size_bytes=stat.st_size,
            modified_ns=stat.st_mtime_ns,
            root_element=parsed["root_element"],
            raw_xml=content,
            parsed_data=parsed["parsed_data"],
            parse_status=parsed["status"],
        )

    def movie(self, title, rating, nfo=None):
        item = MediaItem.objects.create(
            library=self.library, title=title, media_type=MediaItem.MediaType.MOVIE, content_rating=rating
        )
        media_file = MediaFile.objects.create(
            library=self.library, media_item=item, relative_path=f"{title}/{title}.mkv", file_name=f"{title}.mkv"
        )
        record = self.write_nfo(self.library, f"{title}/{title}.nfo", nfo, item, media_file) if nfo else None
        return item, record

    def url(self, library=None):
        return f"/api/libraries/{(library or self.library).id}/ratings/nfo-export/"

    def file_text(self, record):
        return Path(record.library.path, *record.relative_path.split("/")).read_bytes().decode("utf-8")


class ExportTests(_ExportTestCase):
    def test_preview_lists_changes_without_writing(self):
        _item, cars = self.movie("Cars", "G", MOVIE_NFO)
        self.movie("Up", "PG", MOVIE_NFO.replace("NR", "PG"))
        self.movie("Coco", "", MOVIE_NFO)
        self.movie("Brave", "PG")
        response = self.client.get(self.url(), {"kind": "movie"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["writable"])
        self.assertEqual(response.data["summary"], {"write": 1, "add": 0, "unchanged": 1, "no_nfo": 1, "unrated": 1})
        self.assertEqual(response.data["rows"][0]["nfo_rating"], "NR")
        self.assertEqual(self.file_text(cars), MOVIE_NFO)

    def test_apply_writes_only_the_rating(self):
        _item, cars = self.movie("Cars", "G", MOVIE_NFO)
        response = self.client.post(self.url(), {"kind": "movie"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["counts"], {"written": 1, "changed_on_disk": 0, "failed": 0})
        self.assertEqual(self.file_text(cars), MOVIE_NFO.replace("<mpaa>NR</mpaa>", "<mpaa>G</mpaa>"))
        cars.refresh_from_db()
        self.assertEqual(cars.parsed_data["movie"]["mpaa"], "G")
        # Now up to date: a second run writes nothing.
        again = self.client.get(self.url(), {"kind": "movie"}).data
        self.assertEqual(again["files_to_write"], 0)

    def test_series_tvshow_nfo_gets_rating_added(self):
        series = Series.objects.create(library=self.tv, title="Bluey", semantic_key="bluey", content_rating="TV-Y")
        season = Season.objects.create(series=series, season_number=1)
        episode_item = MediaItem.objects.create(library=self.tv, title="E1", media_type=MediaItem.MediaType.TV_EPISODE)
        Episode.objects.create(media_item=episode_item, season=season, episode_number=1)
        MediaFile.objects.create(
            library=self.tv, media_item=episode_item, relative_path="Bluey/Season 01/Bluey - S01E01.mkv", file_name="x.mkv"
        )
        tvshow = self.write_nfo(self.tv, "Bluey/tvshow.nfo", NO_MPAA_NFO)
        response = self.client.post(self.url(self.tv), {"kind": "series"}, format="json")
        self.assertEqual(response.data["counts"]["written"], 1, response.data)
        self.assertEqual(
            self.file_text(tvshow),
            "<tvshow>\r\n\t<title>Bluey</title>\r\n\t<year>2018</year>\r\n\t<mpaa>TV-Y</mpaa>\r\n</tvshow>\r\n",
        )

    def test_file_changed_on_disk_is_skipped(self):
        _item, cars = self.movie("Cars", "G", MOVIE_NFO)
        path = Path(cars.library.path, *cars.relative_path.split("/"))
        edited = MOVIE_NFO.replace("Fast", "Very fast")
        path.write_text(edited, encoding="utf-8")
        os.utime(path, ns=(cars.modified_ns + 5_000_000_000, cars.modified_ns + 5_000_000_000))
        response = self.client.post(self.url(), {"kind": "movie"}, format="json")
        self.assertEqual(response.data["counts"], {"written": 0, "changed_on_disk": 1, "failed": 0})
        self.assertEqual(response.data["problems"][0]["result"], "changed_on_disk")
        self.assertEqual(path.read_text(encoding="utf-8"), edited)

    def test_resaved_file_with_identical_content_is_written(self):
        # Media servers often re-save NFOs unchanged, which only moves the
        # timestamp. That must not block writing the rating.
        _item, cars = self.movie("Cars", "G", MOVIE_NFO)
        path = Path(cars.library.path, *cars.relative_path.split("/"))
        os.utime(path, ns=(cars.modified_ns + 90 * 86_400 * 10**9, cars.modified_ns + 90 * 86_400 * 10**9))
        response = self.client.post(self.url(), {"kind": "movie"}, format="json")
        self.assertEqual(response.data["counts"], {"written": 1, "changed_on_disk": 0, "failed": 0})
        self.assertIn("<mpaa>G</mpaa>", self.file_text(cars))

    def test_line_ending_differences_alone_are_not_a_change(self):
        _item, cars = self.movie("Cars", "G", MOVIE_NFO)
        path = Path(cars.library.path, *cars.relative_path.split("/"))
        path.write_bytes(MOVIE_NFO.replace("\n", "\r\n").encode("utf-8"))
        response = self.client.post(self.url(), {"kind": "movie"}, format="json")
        self.assertEqual(response.data["counts"]["written"], 1)
        self.assertEqual(
            path.read_bytes().decode("utf-8"),
            MOVIE_NFO.replace("\n", "\r\n").replace("<mpaa>NR</mpaa>", "<mpaa>G</mpaa>"),
        )

    def test_unwritable_documents_fail_safely(self):
        _item, broken = self.movie("Cars", "G", "<movie><title>Cars</title></movie>")
        path = Path(broken.library.path, *broken.relative_path.split("/"))
        path.write_text("<movie><title>Cars</title>", encoding="utf-8")
        stat = path.stat()
        NfoFile.objects.filter(id=broken.id).update(
            size_bytes=stat.st_size, modified_ns=stat.st_mtime_ns, raw_xml="<movie><title>Cars</title>"
        )
        response = self.client.post(self.url(), {"kind": "movie"}, format="json")
        self.assertEqual(response.data["counts"]["failed"], 1)
        self.assertEqual(path.read_text(encoding="utf-8"), "<movie><title>Cars</title>")

    def test_batches_with_cursor(self):
        records = [self.movie(f"Movie {number}", "PG", MOVIE_NFO)[1] for number in range(5)]
        first = self.client.post(self.url(), {"kind": "movie", "batch": 2}, format="json").data
        self.assertEqual((first["counts"]["written"], first["remaining"]), (2, 3))
        second = self.client.post(
            self.url(), {"kind": "movie", "batch": 2, "cursor": first["next_cursor"]}, format="json"
        ).data
        self.assertEqual((second["counts"]["written"], second["remaining"]), (2, 1))
        third = self.client.post(
            self.url(), {"kind": "movie", "batch": 2, "cursor": second["next_cursor"]}, format="json"
        ).data
        self.assertEqual((third["counts"]["written"], third["remaining"], third["next_cursor"]), (1, 0, None))
        for record in records:
            self.assertIn("<mpaa>PG</mpaa>", self.file_text(record))
        self.assertEqual(self.client.post(self.url(), {"kind": "movie", "batch": 0}, format="json").status_code, 400)


class SafetyTests(_ExportTestCase):
    def test_read_only_library_is_previewed_but_never_written(self):
        self.library.management_mode = Library.ManagementMode.READ_ONLY
        self.library.save()
        _item, cars = self.movie("Cars", "G", MOVIE_NFO)
        preview = self.client.get(self.url(), {"kind": "movie"}).data
        self.assertFalse(preview["writable"])
        self.assertEqual(preview["files_to_write"], 1)
        response = self.client.post(self.url(), {"kind": "movie"}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertIn("Sidecar Only", response.data["detail"])
        self.assertEqual(self.file_text(cars), MOVIE_NFO)

    def test_paths_outside_library_are_refused(self):
        _item, cars = self.movie("Cars", "G", MOVIE_NFO)
        outside = self.root / "outside.nfo"
        outside.write_text(MOVIE_NFO, encoding="utf-8")
        NfoFile.objects.filter(id=cars.id).update(relative_path="../outside.nfo")
        response = self.client.post(self.url(), {"kind": "movie"}, format="json")
        self.assertEqual(response.data["counts"]["failed"], 1)
        self.assertEqual(outside.read_text(encoding="utf-8"), MOVIE_NFO)

    def test_owner_scope_auth_and_csrf(self):
        theirs = Library.objects.create(
            owner=self.other, name="Theirs", path=str(self.root / "x"), content_type="movies",
            management_mode=Library.ManagementMode.SIDECAR_ONLY,
        )
        self.assertEqual(self.client.get(self.url(theirs)).status_code, 404)
        self.assertEqual(self.client.post(self.url(theirs), {"kind": "movie"}, format="json").status_code, 404)
        self.assertEqual(self.client.get(self.url(), {"kind": "episode"}).status_code, 400)
        _item, cars = self.movie("Cars", "G", MOVIE_NFO)
        client = APIClient(enforce_csrf_checks=True)
        client.login(email="owner@example.com", password="password")
        self.assertEqual(client.post(self.url(), {"kind": "movie"}, format="json").status_code, 403)
        self.assertEqual(self.file_text(cars), MOVIE_NFO)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url()).status_code, (401, 403))


class ManagementModeApiTests(_ExportTestCase):
    def test_owner_can_switch_between_read_only_and_sidecar(self):
        self.library.management_mode = Library.ManagementMode.READ_ONLY
        self.library.save()
        response = self.client.patch(f"/api/libraries/{self.library.id}/", {"management_mode": "sidecar_only"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.library.refresh_from_db()
        self.assertEqual(self.library.management_mode, "sidecar_only")
        response = self.client.patch(f"/api/libraries/{self.library.id}/", {"management_mode": "bogus"}, format="json")
        self.assertEqual(response.status_code, 400)


class UnreachableShareTests(_ExportTestCase):
    def test_unreachable_root_stops_once_with_the_reason(self):
        _item, cars = self.movie("Cars", "G", MOVIE_NFO)
        signin = OSError(None, "The user name or password is incorrect")
        signin.winerror = 1326
        with patch("pathlib.Path.resolve", side_effect=signin):
            preview = self.client.get(self.url(), {"kind": "movie"}).data
            self.assertIn("isn't signed in to that network share", preview["root_error"])
            response = self.client.post(self.url(), {"kind": "movie"}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertIn("user name or password is incorrect", response.data["detail"])
        self.assertEqual(self.file_text(cars), MOVIE_NFO)

    def test_reachable_root_has_no_error(self):
        self.movie("Cars", "G", MOVIE_NFO)
        self.assertIsNone(self.client.get(self.url(), {"kind": "movie"}).data["root_error"])
