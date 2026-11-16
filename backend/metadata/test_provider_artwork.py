"""Choosing provider artwork and saving it beside a movie or series."""

import shutil
import struct
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from catalog.models import (
    ArtworkFile,
    CanonicalFieldState,
    Episode,
    MediaVersion,
    MetadataChangeSet,
    Season,
)
from integrations.crypto import encrypt_secrets
from integrations.models import IntegrationConnection, LibraryIntegration
from integrations.security import RemoteImage
from integrations.tests.test_tmdb import MOVIE_DETAIL
from libraries.models import Library
from media.models import MediaFile, MediaItem
from metadata.services.provider_artwork import sniff_image
from metadata.test_provider_match import _MatchApiTestCase


def png(width=1000, height=1500, tag=b""):
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00" + tag


def jpeg(width=1920, height=1080):
    return (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        + b"\xff\xc0\x00\x11\x08"
        + struct.pack(">HH", height, width)
        + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    )


POSTER = "https://image.tmdb.org/t/p/original/poster-en.jpg"
BACKDROP = "https://image.tmdb.org/t/p/original/backdrop.jpg"


class SniffTests(SimpleTestCase):
    def test_formats_and_dimensions(self):
        self.assertEqual(sniff_image(png(300, 450)), ("png", 300, 450))
        self.assertEqual(sniff_image(jpeg(1920, 1080)), ("jpg", 1920, 1080))
        vp8x = b"RIFF\x00\x00\x00\x00WEBPVP8X" + b"\x0a\x00\x00\x00" + b"\x00\x00\x00\x00" + (799).to_bytes(3, "little") + (599).to_bytes(3, "little")
        self.assertEqual(sniff_image(vp8x), ("webp", 800, 600))

    def test_non_images_are_rejected(self):
        self.assertIsNone(sniff_image(b"<html>not an image</html>"))
        self.assertIsNone(sniff_image(b"\xff\xd8garbage"))


class _ArtworkBase(_MatchApiTestCase):
    def setUp(self):
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        Library.objects.filter(pk=self.library.pk).update(
            path=str(self.tmp / "Movies"), management_mode=Library.ManagementMode.SIDECAR_ONLY
        )
        Library.objects.filter(pk=self.tv.pk).update(
            path=str(self.tmp / "TV"), management_mode=Library.ManagementMode.SIDECAR_ONLY
        )
        self.library.refresh_from_db()
        self.tv.refresh_from_db()
        self.folder = self.tmp / "Movies" / "The Matrix (1999)"
        self.folder.mkdir(parents=True)
        self.add_file(self.movie, "The Matrix (1999)/The Matrix (1999).mkv")

        self.request.return_value = MOVIE_DETAIL
        self.images = {}
        fetch = patch("metadata.services.provider_artwork.fetch_remote_artwork", side_effect=self._fetch)
        self.fetch = fetch.start()
        self.addCleanup(fetch.stop)

    def _fetch(self, *, artwork_url, **kwargs):
        body = self.images.get(artwork_url, png())
        return RemoteImage(body=body, content_type="image/png")

    def add_file(self, item, relative, library=None):
        library = library or item.library
        path = Path(library.path).joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"video")
        media_file = MediaFile.objects.create(
            library=library, media_item=item, relative_path=relative, file_name=path.name, extension=path.suffix[1:],
            size_bytes=5, is_present=True,
        )
        MediaVersion.objects.create(media_item=item, media_file=media_file, name="main", is_primary=True)
        return media_file

    def url(self, kind="movie", target=None):
        return f"/api/metadata-match/{kind}/{(target or self.movie).id}/artwork/"

    def choices(self, **params):
        response = self.client.get(self.url(), {"connection": str(self.connection.id), "source_id": "603", **params})
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def save(self, url=POSTER, *, kind="movie", target=None, **body):
        payload = {
            "connection": str(self.connection.id),
            "source_id": "603",
            "url": url,
            "operation_id": str(uuid.uuid4()),
            **body,
        }
        return self.client.post(self.url(kind, target), payload, format="json")


class ChoiceTests(_ArtworkBase):
    def test_lists_offered_artwork_with_file_names(self):
        data = self.choices()

        kinds = {(item["url"], item["artwork_type"], item["file_name"]) for item in data["items"]}
        self.assertIn((POSTER, "primary", "poster"), kinds)
        self.assertIn((BACKDROP, "backdrop", "fanart"), kinds)
        self.assertTrue(all(item["url"].startswith("https://image.tmdb.org/") for item in data["items"]))
        self.assertEqual(data["folder"], "The Matrix (1999)")
        self.assertTrue(data["writable"])
        poster = next(item for item in data["items"] if item["url"] == POSTER)
        self.assertEqual(poster["thumbnail_url"], "https://image.tmdb.org/t/p/w342/poster-en.jpg")
        # Listing never writes.
        self.assertEqual(list(self.folder.iterdir()), [self.folder / "The Matrix (1999).mkv"])

    def test_shared_movie_folder_is_explained(self):
        other = MediaItem.objects.create(library=self.library, title="Other", media_type=MediaItem.MediaType.MOVIE)
        self.add_file(other, "The Matrix (1999)/Other.mkv")
        data = self.choices()
        self.assertIn("shares its folder", data["folder_error"])
        self.assertEqual(self.save().status_code, 400)

    def test_prefers_the_matched_connection(self):
        response = self.client.get(self.url(), {"prefer": str(self.connection.id), "source_id": "603"})
        self.assertEqual(response.data["connection"]["provider"], "tmdb")
        self.assertTrue(response.data["items"])

    def test_omdb_is_not_an_artwork_source(self):
        omdb = IntegrationConnection.objects.create(
            owner=self.user, name="OMDb", provider="omdb", configuration={},
            encrypted_secrets=encrypt_secrets({"api_key": "abcd1234"}),
        )
        LibraryIntegration.objects.create(library=self.library, connection=omdb, capabilities=["metadata"], priority=50)
        providers = [row["provider"] for row in self.choices()["sources"]]
        self.assertEqual(providers, ["tmdb"])

    def test_other_users_items_are_hidden(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.url()).status_code, 404)
        self.assertEqual(self.save().status_code, 404)


class SaveTests(_ArtworkBase):
    def test_saves_poster_selects_it_and_records_provenance(self):
        response = self.save()

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["path"], "The Matrix (1999)/poster.png")
        self.assertEqual((self.folder / "poster.png").read_bytes(), png())
        artwork = ArtworkFile.objects.get(library=self.library, relative_path="The Matrix (1999)/poster.png")
        self.assertEqual((artwork.target_id, artwork.artwork_type, artwork.is_selected), (self.movie.id, "primary", True))
        state = CanonicalFieldState.objects.get(target_id=self.movie.id, field_name="artwork_primary")
        self.assertEqual((state.source, state.locked), (CanonicalFieldState.Source.PROVIDER, False))
        self.assertEqual(state.value_snapshot["url"], POSTER)
        change = MetadataChangeSet.objects.get(target_id=self.movie.id, source=MetadataChangeSet.Source.PROVIDER)
        self.assertEqual(change.details["provider"], "tmdb")
        self.assertEqual(change.changes["artwork_primary"]["new"]["relative_path"], "The Matrix (1999)/poster.png")

    def test_backdrop_is_saved_as_fanart(self):
        self.images[BACKDROP] = jpeg()
        response = self.save(BACKDROP)
        self.assertEqual(response.data["path"], "The Matrix (1999)/fanart.jpg")

    def test_existing_artwork_needs_confirmation_and_is_kept_as_a_backup(self):
        (self.folder / "folder.jpg").write_bytes(b"my own poster")

        refused = self.save()
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.data["code"], "existing_artwork")
        self.assertIn("folder.jpg", refused.data["detail"])
        self.assertFalse((self.folder / "poster.png").exists())

        response = self.save(replace=True)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse((self.folder / "folder.jpg").exists())
        backup = self.folder / Path(response.data["backups"][0]["to"]).name
        self.assertTrue(backup.name.startswith("folder.libraryforge-backup-"))
        self.assertEqual(backup.read_bytes(), b"my own poster")

    def test_replacing_our_own_earlier_save_needs_no_confirmation(self):
        self.assertEqual(self.save().status_code, 200)
        self.images["https://image.tmdb.org/t/p/original/poster-none.jpg"] = png(800, 1200)

        response = self.save("https://image.tmdb.org/t/p/original/poster-none.jpg")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["backups"], [])
        self.assertEqual((self.folder / "poster.png").read_bytes(), png(800, 1200))
        self.assertEqual(sorted(path.name for path in self.folder.iterdir()), ["The Matrix (1999).mkv", "poster.png"])

    def test_an_edited_earlier_save_is_treated_as_yours(self):
        self.save()
        (self.folder / "poster.png").write_bytes(png(10_00, 1500, tag=b"edited"))
        self.assertEqual(self.save().data["code"], "existing_artwork")

    def test_urls_not_offered_are_refused(self):
        response = self.save("https://image.tmdb.org/t/p/original/not-offered.jpg")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "not_offered")
        self.fetch.assert_not_called()

    def test_downloads_that_arent_images_are_refused(self):
        self.images[POSTER] = b"<html>error page</html>"
        response = self.save()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(self.folder.iterdir()), [self.folder / "The Matrix (1999).mkv"])

    def test_failure_puts_the_folder_back(self):
        (self.folder / "poster.jpg").write_bytes(b"original")
        with (
            patch("metadata.services.provider_artwork._record", side_effect=RuntimeError("database down")),
            self.assertRaises(RuntimeError),
        ):
            self.save(replace=True)
        self.assertEqual(sorted(path.name for path in self.folder.iterdir()), ["The Matrix (1999).mkv", "poster.jpg"])
        self.assertEqual((self.folder / "poster.jpg").read_bytes(), b"original")

    def test_repeated_operation_is_replayed(self):
        operation = str(uuid.uuid4())
        first = self.save(operation_id=operation)
        second = self.save(operation_id=operation)
        self.assertTrue(second.data["replayed"])
        self.assertEqual(first.data["path"], second.data["path"])
        self.assertEqual(self.fetch.call_count, 1)

    def test_read_only_library_is_refused(self):
        Library.objects.filter(pk=self.library.pk).update(management_mode=Library.ManagementMode.READ_ONLY)
        response = self.save()
        self.assertEqual(response.status_code, 409)
        self.assertIn("Read Only", response.data["detail"])


class FanartSeriesTests(_ArtworkBase):
    def setUp(self):
        super().setUp()
        season = Season.objects.create(series=self.series, season_number=1, title="Season 1")
        item = MediaItem.objects.create(library=self.tv, title="Pilot", media_type=MediaItem.MediaType.TV_EPISODE)
        Episode.objects.create(media_item=item, season=season, episode_number=1)
        self.add_file(item, "Breaking Bad/Season 01/S01E01.mkv", library=self.tv)
        self.show = self.tmp / "TV" / "Breaking Bad"
        (self.show / "season01-poster.jpg").write_bytes(b"season poster")

        self.fanart = IntegrationConnection.objects.create(
            owner=self.user, name="Fanart", provider="fanart", configuration={},
            encrypted_secrets=encrypt_secrets({"api_key": "abcdef0123456789"}),
        )
        LibraryIntegration.objects.create(library=self.tv, connection=self.fanart, capabilities=["artwork"], priority=50)
        fanart = patch("integrations.providers.fanart.request_json", return_value={
            "name": "Breaking Bad",
            "tvposter": [
                {"id": "1", "url": "https://assets.fanart.tv/fanart/tv/81189/tvposter/bb-de.jpg", "lang": "de", "likes": "9"},
                {"id": "2", "url": "https://assets.fanart.tv/fanart/tv/81189/tvposter/bb.jpg", "lang": "en", "likes": "3"},
            ],
            "hdtvlogo": [{"id": "3", "url": "https://assets.fanart.tv/fanart/tv/81189/hdtvlogo/bb.png", "lang": "en"}],
            "seasonposter": [{"id": "4", "url": "https://assets.fanart.tv/fanart/tv/81189/seasonposter/s1.jpg", "season": "1"}],
            "tvbanner": [{"id": "5", "url": "http://insecure.example/banner.jpg", "lang": "en"}],
        })
        self.fanart_request = fanart.start()
        self.addCleanup(fanart.stop)

    def test_fanart_lists_by_tvdb_id_and_saves_beside_the_series(self):
        response = self.client.get(
            self.url("series", self.series), {"connection": str(self.fanart.id), "tvdb": "81189"}
        )
        self.assertEqual(response.status_code, 200, response.data)
        urls = [item["url"] for item in response.data["items"]]
        # English first, season art and insecure URLs left out.
        self.assertEqual(urls[0], "https://assets.fanart.tv/fanart/tv/81189/tvposter/bb.jpg")
        self.assertEqual(len(urls), 3)
        self.assertEqual(
            response.data["items"][0]["thumbnail_url"], "https://assets.fanart.tv/bigpreview/tv/81189/tvposter/bb.jpg"
        )
        self.assertIn("api_key=abcdef0123456789", self.fanart_request.call_args.args[0])
        self.assertIn("/v3.2/tv/81189", self.fanart_request.call_args.args[0])

        saved = self.client.post(
            self.url("series", self.series),
            {
                "connection": str(self.fanart.id),
                "ids": {"tvdb": "81189"},
                "url": "https://assets.fanart.tv/fanart/tv/81189/hdtvlogo/bb.png",
                "operation_id": str(uuid.uuid4()),
            },
            format="json",
        )
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(saved.data["path"], "Breaking Bad/logo.png")
        # Season art in the series folder is never touched.
        self.assertEqual((self.show / "season01-poster.jpg").read_bytes(), b"season poster")

    def test_series_poster_ignores_season_posters(self):
        response = self.client.post(
            self.url("series", self.series),
            {
                "connection": str(self.fanart.id),
                "ids": {"tvdb": "81189"},
                "url": "https://assets.fanart.tv/fanart/tv/81189/tvposter/bb.jpg",
                "operation_id": str(uuid.uuid4()),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["backups"], [])
