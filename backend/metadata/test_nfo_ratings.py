"""Importing content ratings from indexed NFO files."""

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APIClient, APITestCase

from catalog.models import (
    CanonicalFieldState,
    Episode,
    MetadataChangeSet,
    Season,
    Series,
)
from libraries.models import Library
from media.models import MediaFile, MediaItem
from metadata.models import NfoFile
from metadata.services.nfo_ratings import normalize_nfo_rating


class NormalizeTests(SimpleTestCase):
    def test_kodi_and_jellyfin_forms(self):
        for raw, expected in [
            ("PG-13", "PG-13"),
            (" pg-13 ", "PG-13"),
            ("Rated R", "R"),
            ("US:PG", "PG"),
            ("USA:Rated PG-13", "PG-13"),
            ("US:PG-13 / UK:12A", "PG-13"),
            ("tv-ma", "TV-MA"),
            ("Not Rated", "Not Rated"),
            ("UK:15", "15"),
            ("", ""),
            (None, ""),
            (["", "TV-Y7"], "TV-Y7"),
            ({"value": "R"}, ""),
            ("x" * 80, ""),
        ]:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_nfo_rating(raw), expected)


class _NfoImportTestCase(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(email="owner@example.com", password="password")
        self.other = user_model.objects.create_user(email="other@example.com", password="password")
        self.client.force_authenticate(self.user)
        self.movies = Library.objects.create(owner=self.user, name="Movies", path="/m", content_type="movies")
        self.tv = Library.objects.create(owner=self.user, name="TV", path="/t", content_type="tv")

    def movie(self, title, *, rating="", nfo_rating=None, nfo_name=None, extra_nfos=()):
        item = MediaItem.objects.create(
            library=self.movies, title=title, media_type=MediaItem.MediaType.MOVIE, content_rating=rating
        )
        media_file = MediaFile.objects.create(
            library=self.movies, media_item=item, relative_path=f"{title}/{title}.mkv", file_name=f"{title}.mkv"
        )
        if nfo_rating is not None:
            self.nfo(self.movies, f"{title}/{nfo_name or title + '.nfo'}", "movie", nfo_rating, item, media_file)
        for name, value in extra_nfos:
            self.nfo(self.movies, f"{title}/{name}", "movie", value, item, media_file)
        return item

    def nfo(self, library, path, root, rating, item=None, media_file=None):
        body = {"title": "x"}
        if rating:
            body["mpaa"] = rating
        return NfoFile.objects.create(
            library=library,
            media_item=item,
            media_file=media_file,
            relative_path=path,
            file_name=path.rsplit("/", 1)[-1],
            root_element=root,
            parsed_data={root: body},
            parse_status=NfoFile.ParseStatus.OK,
        )

    def series(self, title, *, rating="", nfo_rating=None, episodes=2, nfo_dir=None):
        series = Series.objects.create(library=self.tv, title=title, semantic_key=title.lower(), content_rating=rating)
        season = Season.objects.create(series=series, season_number=1)
        for number in range(1, episodes + 1):
            item = MediaItem.objects.create(library=self.tv, title=f"E{number}", media_type=MediaItem.MediaType.TV_EPISODE)
            Episode.objects.create(media_item=item, season=season, episode_number=number)
            MediaFile.objects.create(
                library=self.tv,
                media_item=item,
                relative_path=f"{title}/Season 01/{title} - S01E0{number}.mkv",
                file_name=f"{title} - S01E0{number}.mkv",
            )
        if nfo_rating is not None:
            self.nfo(self.tv, f"{nfo_dir or title}/tvshow.nfo", "tvshow", nfo_rating)
        return series

    def lock(self, obj, source=CanonicalFieldState.Source.MANUAL, target_type=CanonicalFieldState.TargetType.MEDIA_ITEM):
        CanonicalFieldState.objects.create(
            target_type=target_type, target_id=obj.id, field_name="content_rating", source=source, locked=True
        )

    def url(self, library):
        return f"/api/libraries/{library.id}/ratings/nfo-import/"


class MovieImportTests(_NfoImportTestCase):
    def setUp(self):
        super().setUp()
        self.empty = self.movie("Cars", nfo_rating="Rated G")
        self.same = self.movie("Up", rating="PG", nfo_rating="pg")
        self.conflict = self.movie("Heat", rating="PG-13", nfo_rating="R")
        self.locked = self.movie("Alien", nfo_rating="R")
        self.lock(self.locked)
        self.no_rating = self.movie("Coco", nfo_rating="")
        self.no_nfo = self.movie("Brave")
        self.disagree = self.movie("Rabid", nfo_rating="NR", extra_nfos=[("movie.nfo", "Not Rated")])
        self.prefers_named = self.movie("Moana", nfo_rating="PG", extra_nfos=[("movie.nfo", "")])

    def test_preview_classifies_without_writing(self):
        response = self.client.get(self.url(self.movies), {"kind": "movie"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            response.data["summary"],
            {
                "set": 2,
                "update": 0,
                "unchanged": 1,
                "conflict": 1,
                "locked": 1,
                "nfo_disagree": 1,
                "no_rating_in_nfo": 1,
                "no_nfo": 1,
            },
        )
        actions = {row["title"]: row for row in response.data["rows"]}
        self.assertEqual(actions["Heat"]["action"], "conflict")
        self.assertEqual(actions["Rabid"]["other_values"], ["NR", "Not Rated"])
        self.assertEqual(actions["Cars"]["nfo_rating"], "G")
        self.assertEqual(MetadataChangeSet.objects.count(), 0)
        self.empty.refresh_from_db()
        self.assertEqual(self.empty.content_rating, "")

    def test_apply_fills_only_empty_ratings_with_provenance(self):
        response = self.client.post(self.url(self.movies), {"kind": "movie"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["written"], 2)
        for item, expected in (
            (self.empty, "G"),
            (self.prefers_named, "PG"),
            (self.same, "PG"),
            (self.conflict, "PG-13"),
            (self.locked, ""),
            (self.disagree, ""),
            (self.no_rating, ""),
        ):
            with self.subTest(title=item.title):
                item.refresh_from_db()
                self.assertEqual(item.content_rating, expected)

        state = CanonicalFieldState.objects.get(target_id=self.empty.id, field_name="content_rating")
        self.assertEqual((state.source, state.locked, state.source_ref), ("nfo", False, "Cars/Cars.nfo"))
        change_set = MetadataChangeSet.objects.get(target_id=self.empty.id)
        self.assertEqual(change_set.changes, {"content_rating": {"old": "", "new": "G"}})
        self.assertEqual(change_set.changed_by, self.user)
        self.assertEqual(MetadataChangeSet.objects.count(), 2)

        # Running it again changes nothing.
        again = self.client.post(self.url(self.movies), {"kind": "movie"}, format="json")
        self.assertEqual(again.data["written"], 0)
        self.assertEqual(again.data["summary"]["set"], 0)
        self.assertEqual(MetadataChangeSet.objects.count(), 2)

    def test_nfo_sourced_rating_follows_nfo_changes(self):
        self.client.post(self.url(self.movies), {"kind": "movie"}, format="json")
        nfo = NfoFile.objects.get(relative_path="Cars/Cars.nfo")
        nfo.parsed_data = {"movie": {"mpaa": "PG"}}
        nfo.save()
        preview = self.client.get(self.url(self.movies), {"kind": "movie"}).data
        self.assertEqual(preview["summary"]["update"], 1)
        self.client.post(self.url(self.movies), {"kind": "movie"}, format="json")
        self.empty.refresh_from_db()
        self.assertEqual(self.empty.content_rating, "PG")

    def test_provider_and_manual_ratings_are_never_replaced(self):
        provider = self.movie("Dune", rating="PG-13", nfo_rating="R")
        self.lock(provider, source=CanonicalFieldState.Source.PROVIDER)
        self.client.post(self.url(self.movies), {"kind": "movie"}, format="json")
        provider.refresh_from_db()
        self.assertEqual(provider.content_rating, "PG-13")
        self.assertEqual(
            CanonicalFieldState.objects.get(target_id=provider.id, field_name="content_rating").source, "provider"
        )


class SeriesImportTests(_NfoImportTestCase):
    def test_tvshow_nfo_is_linked_by_folder(self):
        bluey = self.series("Bluey", nfo_rating="TV-Y")
        nested = self.series("Nested", nfo_rating="TV-PG")
        unlinked = self.series("Elsewhere", nfo_rating="TV-MA", nfo_dir="Some Other Show")
        no_rating = self.series("Quiet", nfo_rating="")
        preview = self.client.get(self.url(self.tv), {"kind": "series"}).data
        self.assertEqual(preview["summary"]["set"], 2)
        self.assertEqual(preview["summary"]["no_nfo"], 1)
        self.assertEqual(preview["summary"]["no_rating_in_nfo"], 1)

        self.client.post(self.url(self.tv), {"kind": "series"}, format="json")
        for series, expected in ((bluey, "TV-Y"), (nested, "TV-PG"), (unlinked, ""), (no_rating, "")):
            with self.subTest(title=series.title):
                series.refresh_from_db()
                self.assertEqual(series.content_rating, expected)
        state = CanonicalFieldState.objects.get(target_id=bluey.id, field_name="content_rating")
        self.assertEqual((state.target_type, state.source_ref), ("series", "Bluey/tvshow.nfo"))


class AccessTests(_NfoImportTestCase):
    def test_owner_scoped_and_validated(self):
        theirs = Library.objects.create(owner=self.other, name="Theirs", path="/x", content_type="movies")
        self.assertEqual(self.client.get(self.url(theirs)).status_code, 404)
        self.assertEqual(self.client.post(self.url(theirs), {"kind": "movie"}, format="json").status_code, 404)
        self.assertEqual(self.client.get(self.url(self.movies), {"kind": "episode"}).status_code, 400)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url(self.movies)).status_code, (401, 403))

    def test_read_only_library_is_supported_and_csrf_enforced(self):
        self.movies.management_mode = Library.ManagementMode.READ_ONLY
        self.movies.save()
        item = self.movie("Cars", nfo_rating="G")
        client = APIClient(enforce_csrf_checks=True)
        client.login(email="owner@example.com", password="password")
        self.assertEqual(client.post(self.url(self.movies), {"kind": "movie"}, format="json").status_code, 403)
        response = self.client.post(self.url(self.movies), {"kind": "movie"}, format="json")
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.content_rating, "G")
