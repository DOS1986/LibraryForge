"""Writing LibraryForge fields into NFOs, and editing online videos and channels."""

import datetime
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from catalog.models import (
    CanonicalFieldState,
    Channel,
    Episode,
    MediaVersion,
    MetadataChangeSet,
    OnlineVideo,
    Season,
    Series,
)
from libraries.models import Library
from media.models import MediaFile, MediaItem
from metadata.models import NfoFile
from metadata.services import secure_nfo
from metadata.services.nfo_fields import read_nfo_fields, set_nfo_fields

RICH = """<?xml version="1.0" encoding="utf-8" standalone="yes"?>\r
<movie>\r
  <!-- kept: <title>not this</title> -->\r
  <title>Old Title</title>\r
  <plot><![CDATA[Old <b>plot</b>]]></plot>\r
  <genre>Action</genre>\r
  <genre>Drama</genre>\r
  <actor>\r
    <name>Keanu</name>\r
    <title>nested, never touched</title>\r
  </actor>\r
  <custom attr="1">keep me</custom>\r
  <mpaa/>\r
</movie>\r
"""


class FieldEditorTests(SimpleTestCase):
    def test_changes_only_the_chosen_top_level_tags(self):
        updated = set_nfo_fields(RICH, "movie", {"title": "New & Improved", "genre": ["Sci-Fi"], "mpaa": "PG-13"})

        self.assertIn("<title>New &amp; Improved</title>", updated)
        self.assertIn("<title>nested, never touched</title>", updated)
        self.assertIn("<!-- kept: <title>not this</title> -->", updated)
        self.assertIn('<custom attr="1">keep me</custom>', updated)
        self.assertIn("<plot><![CDATA[Old <b>plot</b>]]></plot>", updated)
        self.assertIn("  <genre>Sci-Fi</genre>\r\n", updated)
        self.assertNotIn("Drama", updated)
        self.assertIn("<mpaa>PG-13</mpaa>", updated)
        self.assertNotIn("\n\n", updated.replace("\r\n", "\n"))
        fields = read_nfo_fields(updated, "movie")
        self.assertEqual(fields["genre"], ["Sci-Fi"])

    def test_adds_missing_tags_before_the_closing_tag_and_removes_empty_ones(self):
        updated = set_nfo_fields(RICH, "movie", {"tagline": "Free your mind", "plot": ""})
        self.assertIn("  <tagline>Free your mind</tagline>\r\n</movie>", updated)
        self.assertNotIn("<plot>", updated)

    def test_duplicate_scalar_tags_collapse_to_one(self):
        raw = "<movie>\n  <plot>a</plot>\n  <plot>b</plot>\n</movie>\n"
        self.assertEqual(set_nfo_fields(raw, "movie", {"plot": "c"}), "<movie>\n  <plot>c</plot>\n</movie>\n")

    def test_wrong_root_is_refused(self):
        with self.assertRaises(ValueError):
            set_nfo_fields("<tvshow><title>x</title></tvshow>", "movie", {"title": "y"})


class _Base(APITestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        user_model = get_user_model()
        self.user = user_model.objects.create_user(email="owner@example.com", password="password")
        self.other = user_model.objects.create_user(email="other@example.com", password="password")
        self.client.force_authenticate(self.user)
        self.library = Library.objects.create(
            owner=self.user, name="Movies", path=str(self.root / "movies"), content_type="movies",
            management_mode=Library.ManagementMode.SIDECAR_ONLY,
        )

    def file(self, library, item, relative):
        path = Path(library.path, *relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"video")
        media_file = MediaFile.objects.create(
            library=library, media_item=item, relative_path=relative, file_name=path.name, extension=path.suffix[1:], is_present=True
        )
        MediaVersion.objects.create(media_item=item, media_file=media_file, name="main", is_primary=True)
        return media_file

    def indexed(self, library, relative, content, item=None, media_file=None):
        path = Path(library.path, *relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))
        parsed = secure_nfo.parse_nfo_content(content)
        return NfoFile.objects.create(
            library=library, media_item=item, media_file=media_file, relative_path=relative,
            file_name=relative.rsplit("/", 1)[-1], root_element=parsed["root_element"], raw_xml=content,
            parsed_data=parsed["parsed_data"], parse_status=parsed["status"],
        )

    def movie(self, title="The Matrix", nfo=None):
        item = MediaItem.objects.create(
            library=self.library, title=title, media_type=MediaItem.MediaType.MOVIE, description="Neo wakes up.",
            content_rating="R", genres=["Sci-Fi", "Action"], release_date=datetime.date(1999, 3, 31),
        )
        media_file = self.file(self.library, item, f"{title}/{title}.mkv")
        record = self.indexed(self.library, f"{title}/{title}.nfo", nfo, item, media_file) if nfo else None
        return item, record

    def url(self, kind, obj):
        return f"/api/catalog-editor/{kind}/{obj.id}/nfo/"


class ItemNfoTests(_Base):
    def test_compare_and_write_changed_fields_only(self):
        item, record = self.movie(nfo=RICH)

        comparison = self.client.get(self.url("movies", item)).data
        rows = {row["tag"]: row for row in comparison["fields"]}
        self.assertEqual((rows["title"]["status"], rows["title"]["nfo"]), ("different", "Old Title"))
        self.assertEqual(rows["genre"]["nfo"], ["Action", "Drama"])
        self.assertEqual(rows["tagline"]["status"], "empty")
        self.assertTrue(comparison["nfo"]["exists"])

        response = self.client.post(self.url("movies", item), {"fields": ["title", "mpaa"]}, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["written"], ["mpaa", "title"])
        text = Path(self.library.path, *record.relative_path.split("/")).read_bytes().decode()
        self.assertIn("<title>The Matrix</title>", text)
        self.assertIn("<mpaa>R</mpaa>", text)
        self.assertIn("<genre>Drama</genre>", text)  # not chosen, so kept
        self.assertIn("\r\n", text)
        record.refresh_from_db()
        self.assertIn("The Matrix", record.raw_xml)

    def test_nfo_values_are_never_erased(self):
        item, record = self.movie(nfo=RICH.replace("<mpaa/>", "<mpaa/>\r\n  <tagline>Kept</tagline>"))
        rows = {row["tag"]: row for row in self.client.get(self.url("movies", item)).data["fields"]}
        self.assertEqual(rows["tagline"]["status"], "nfo_only")

        response = self.client.post(self.url("movies", item), {"fields": ["tagline", "title"]}, format="json")

        self.assertEqual(response.data["written"], ["title"])
        text = Path(self.library.path, *record.relative_path.split("/")).read_bytes().decode()
        self.assertIn("<tagline>Kept</tagline>", text)

    def test_missing_nfo_is_created_beside_the_video(self):
        item, _record = self.movie()

        comparison = self.client.get(self.url("movies", item)).data
        self.assertEqual((comparison["nfo"]["exists"], comparison["nfo"]["path"]), (False, "The Matrix/The Matrix.nfo"))

        response = self.client.post(self.url("movies", item), {}, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["result"], "created")
        fields = read_nfo_fields(Path(self.library.path, "The Matrix", "The Matrix.nfo").read_text("utf-8"), "movie")
        self.assertEqual(fields["title"], ["The Matrix"])
        self.assertEqual(fields["genre"], ["Sci-Fi", "Action"])
        self.assertEqual(fields["premiered"], ["1999-03-31"])
        self.assertTrue(NfoFile.objects.get(media_item=item).is_generated)
        self.assertTrue(response.data["comparison"]["nfo"]["exists"])

    def test_unindexed_file_is_never_replaced(self):
        item, _record = self.movie()
        Path(self.library.path, "The Matrix", "The Matrix.nfo").write_text("<movie><title>mine</title></movie>")
        response = self.client.post(self.url("movies", item), {}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertIn("isn't indexed", response.data["detail"])

    def test_changed_on_disk_is_refused(self):
        item, record = self.movie(nfo=RICH)
        Path(self.library.path, *record.relative_path.split("/")).write_text(RICH.replace("Old Title", "Edited"))
        response = self.client.post(self.url("movies", item), {"fields": ["title"]}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertIn("Rescan", response.data["detail"])

    def test_read_only_library_is_refused(self):
        item, _record = self.movie(nfo=RICH)
        Library.objects.filter(pk=self.library.pk).update(management_mode=Library.ManagementMode.READ_ONLY)
        self.assertEqual(self.client.post(self.url("movies", item), {}, format="json").status_code, 409)

    def test_unknown_fields_and_other_users(self):
        item, _record = self.movie(nfo=RICH)
        self.assertEqual(self.client.post(self.url("movies", item), {"fields": ["actor"]}, format="json").status_code, 400)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.url("movies", item)).status_code, 404)

    def test_series_and_episode_nfos(self):
        tv = Library.objects.create(
            owner=self.user, name="TV", path=str(self.root / "tv"), content_type="tv",
            management_mode=Library.ManagementMode.SIDECAR_ONLY,
        )
        series = Series.objects.create(library=tv, title="Bluey", semantic_key="bluey", start_year=2018, content_rating="TV-Y")
        season = Season.objects.create(series=series, season_number=1, title="Season 1")
        item = MediaItem.objects.create(library=tv, title="Magic Xylophone", media_type=MediaItem.MediaType.TV_EPISODE)
        episode = Episode.objects.create(media_item=item, season=season, episode_number=1, air_date=datetime.date(2018, 10, 1))
        self.file(tv, item, "Bluey/Season 01/Bluey S01E01.mkv")

        series_response = self.client.post(self.url("series", series), {}, format="json")
        self.assertEqual(series_response.status_code, 200, series_response.data)
        self.assertEqual(series_response.data["path"], "Bluey/tvshow.nfo")
        show = read_nfo_fields(Path(tv.path, "Bluey", "tvshow.nfo").read_text("utf-8"), "tvshow")
        self.assertEqual((show["title"], show["mpaa"], show["year"]), (["Bluey"], ["TV-Y"], ["2018"]))

        episode_response = self.client.post(self.url("episodes", episode), {}, format="json")
        self.assertEqual(episode_response.data["path"], "Bluey/Season 01/Bluey S01E01.nfo")
        details = read_nfo_fields(Path(tv.path, "Bluey", "Season 01", "Bluey S01E01.nfo").read_text("utf-8"), "episodedetails")
        self.assertEqual((details["season"], details["episode"], details["aired"]), (["1"], ["1"], ["2018-10-01"]))


class CreateMissingTests(_Base):
    def test_preview_and_batched_creation(self):
        self.movie("Cars")
        self.movie("Up")
        self.movie("Has One", nfo="<movie><title>Has One</title></movie>")
        url = f"/api/libraries/{self.library.id}/nfo-create/"

        preview = self.client.get(url, {"kind": "movie"}).data
        self.assertEqual((preview["missing"], preview["ready"]), (2, 2))

        first = self.client.post(url, {"kind": "movie", "batch": 1}, format="json").data
        self.assertEqual((first["created"], first["remaining"]), (1, 1))
        second = self.client.post(url, {"kind": "movie", "cursor": first["next_cursor"], "batch": 1}, format="json").data
        self.assertEqual((second["created"], second["remaining"], second["next_cursor"]), (1, 0, None))
        self.assertTrue(Path(self.library.path, "Cars", "Cars.nfo").exists())
        self.assertEqual(self.client.get(url, {"kind": "movie"}).data["missing"], 0)


class OnlineVideoEditorTests(_Base):
    def setUp(self):
        super().setUp()
        self.youtube = Library.objects.create(owner=self.user, name="Youtube", path=str(self.root / "yt"), content_type="online_video")
        self.channel = Channel.objects.create(library=self.youtube, provider="youtube", source_id="UC1", title="Kids")
        item = MediaItem.objects.create(library=self.youtube, title="Old", media_type=MediaItem.MediaType.ONLINE_VIDEO)
        self.video = OnlineVideo.objects.create(
            library=self.youtube, media_item=item, channel=self.channel, provider="youtube", source_id="vid1",
            upload_date=datetime.date(2024, 5, 12), tags=["a"],
        )

    def test_edit_video_locks_fields_and_records_history(self):
        url = f"/api/catalog-editor/online-videos/{self.video.id}/"
        response = self.client.patch(
            url,
            {"title": "Wheels on the Bus", "content_rating": "tv-y", "upload_date": "2024-05-13", "tags": ["Songs", "Songs", " Kids "]},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["title"], "Wheels on the Bus")
        self.assertEqual(response.data["content_rating"], "TV-Y")
        self.assertEqual(response.data["tags"], ["Songs", "Kids"])
        self.video.refresh_from_db()
        self.assertEqual(self.video.media_item.release_date, datetime.date(2024, 5, 13))
        state = CanonicalFieldState.objects.get(target_id=self.video.media_item.id, field_name="title")
        self.assertEqual((state.source, state.locked), (CanonicalFieldState.Source.MANUAL, True))
        self.assertTrue(CanonicalFieldState.objects.get(target_id=self.video.id, field_name="upload_date").locked)
        self.assertEqual(MetadataChangeSet.objects.filter(source=MetadataChangeSet.Source.MANUAL).count(), 2)

    def test_validation(self):
        url = f"/api/catalog-editor/online-videos/{self.video.id}/"
        self.assertEqual(self.client.patch(url, {"title": ""}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"upload_date": "May 5"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"source_id": "x"}, format="json").status_code, 400)

    def test_edit_channel(self):
        url = f"/api/catalog-editor/channels/{self.channel.id}/"
        response = self.client.patch(url, {"title": "Kids Songs", "content_rating": "TV-Y"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data["title"], response.data["video_count"]), ("Kids Songs", 1))
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
