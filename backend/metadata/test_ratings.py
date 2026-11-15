"""Library rating coverage and reviewed rating suggestions."""

import uuid

from catalog.models import CanonicalFieldState, MetadataChangeSet, Series
from integrations.tests.test_tmdb import (
    MOVIE_DETAIL,
    MOVIE_SEARCH,
    SERIES_DETAIL,
    TV_SEARCH,
)
from libraries.models import Library
from media.models import MediaItem
from metadata.services.ratings import rating_status
from metadata.test_provider_match import _MatchApiTestCase


class RatingStatusTests(_MatchApiTestCase):
    def test_rating_status(self):
        self.assertEqual(rating_status(""), "missing")
        self.assertEqual(rating_status(None), "missing")
        self.assertEqual(rating_status("PG"), "rated")
        self.assertEqual(rating_status("tv-y7"), "rated")
        self.assertEqual(rating_status("15"), "unrecognized")
        self.assertEqual(rating_status("NR"), "unrecognized")


class CoverageTests(_MatchApiTestCase):
    def setUp(self):
        super().setUp()
        for title, rating in (("Cars", "G"), ("Up", "pg"), ("Paddington", "15"), ("Frozen", "")):
            MediaItem.objects.create(
                library=self.library, title=title, media_type=MediaItem.MediaType.MOVIE, content_rating=rating
            )
        MediaItem.objects.create(library=self.library, title="Pilot", media_type=MediaItem.MediaType.TV_EPISODE)
        Series.objects.create(library=self.tv, title="Bluey", semantic_key="bluey", content_rating="TV-Y")

    def coverage(self, library=None, **params):
        library = library or self.library
        return self.client.get(f"/api/libraries/{library.id}/ratings/", params)

    def test_summary_counts_movies_and_series(self):
        response = self.coverage()
        self.assertEqual(response.status_code, 200, response.data)
        # The Matrix (from setUp) + Frozen are missing; Paddington's "15" is unrecognized.
        self.assertEqual(response.data["summary"]["movie"], {"total": 5, "rated": 2, "missing": 2, "unrecognized": 1})
        self.assertEqual(response.data["summary"]["series"], {"total": 0, "rated": 0, "missing": 0, "unrecognized": 0})
        tv = self.coverage(self.tv, kind="series").data
        self.assertEqual(tv["summary"]["series"], {"total": 2, "rated": 1, "missing": 1, "unrecognized": 0})
        self.request.assert_not_called()

    def test_status_filters_and_search(self):
        titles = lambda **params: [row["title"] for row in self.coverage(**params).data["results"]]
        self.assertEqual(titles(status="missing"), ["Frozen", "The Matrix"])
        self.assertEqual(titles(status="unrecognized"), ["Paddington"])
        self.assertEqual(titles(status="rated"), ["Cars", "Up"])
        self.assertEqual(titles(search="pad"), ["Paddington"])
        self.assertNotIn("Pilot", titles())

    def test_rows_include_year_status_and_source(self):
        CanonicalFieldState.objects.create(
            target_type=CanonicalFieldState.TargetType.MEDIA_ITEM,
            target_id=self.movie.id,
            field_name="content_rating",
            source=CanonicalFieldState.Source.MANUAL,
            locked=True,
        )
        row = next(item for item in self.coverage().data["results"] if item["title"] == "The Matrix")
        self.assertEqual(row["year"], 1999)
        self.assertEqual(row["status"], "missing")
        self.assertEqual(row["source"], "manual")
        self.assertTrue(row["locked"])

    def test_pagination_and_validation(self):
        data = self.coverage(page_size=2).data
        self.assertEqual((data["total"], len(data["results"]), data["next_page"]), (5, 2, 2))
        self.assertIsNone(self.coverage(page_size=2, page=3).data["next_page"])
        for params in ({"kind": "episode"}, {"status": "bogus"}, {"page": "x"}, {"page_size": "500"}):
            with self.subTest(params=params):
                self.assertEqual(self.coverage(**params).status_code, 400)

    def test_library_is_owner_scoped(self):
        theirs = Library.objects.create(owner=self.other, name="Theirs", path="/t", content_type="movies")
        self.assertEqual(self.coverage(theirs).status_code, 404)
        self.client.force_authenticate(None)
        self.assertIn(self.coverage().status_code, (401, 403))


class SuggestionTests(_MatchApiTestCase):
    def setUp(self):
        super().setUp()
        self.detail = MOVIE_DETAIL
        self.request.side_effect = lambda url, **kwargs: (
            MOVIE_SEARCH if "/search/movie" in url
            else TV_SEARCH if "/search/tv" in url
            else SERIES_DETAIL if "/tv/" in url
            else self.detail
        )

    def suggest(self, ids, library=None, kind="movie"):
        library = library or self.library
        return self.client.get(
            f"/api/libraries/{library.id}/ratings/suggestions/", {"kind": kind, "ids": ",".join(str(i) for i in ids)}
        )

    def test_confident_match_suggests_rating_and_applies_through_apply_endpoint(self):
        before = MetadataChangeSet.objects.count()
        response = self.suggest([self.movie.id])
        self.assertEqual(response.status_code, 200, response.data)
        suggestion = response.data["results"][0]
        self.assertEqual(suggestion["status"], "suggested")
        self.assertEqual(suggestion["rating"], "R")
        self.assertEqual(suggestion["candidate"]["source_id"], "603")
        self.assertEqual(suggestion["apply"]["fields"], ["content_rating"])
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.content_rating, "")
        self.assertEqual(MetadataChangeSet.objects.count(), before)

        apply = self.client.post(
            f"/api/metadata-match/movie/{self.movie.id}/apply/",
            {**suggestion["apply"], "operation_id": str(uuid.uuid4())},
            format="json",
        )
        self.assertEqual(apply.status_code, 200, apply.data)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.content_rating, "R")
        state = CanonicalFieldState.objects.get(target_id=self.movie.id, field_name="content_rating")
        self.assertEqual((state.source, state.locked), ("provider", True))
        self.assertEqual(MetadataChangeSet.objects.get().changes, {"content_rating": {"old": "", "new": "R"}})

    def test_series_suggestion(self):
        response = self.suggest([self.series.id], library=self.tv, kind="series")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["results"][0]["rating"], "TV-MA")

    def test_unconfident_match_needs_review(self):
        inception = MediaItem.objects.create(
            library=self.library,
            title="Inception",
            media_type=MediaItem.MediaType.MOVIE,
            canonical_metadata={"semantic": {"year": 2010}},
        )
        suggestion = self.suggest([inception.id]).data["results"][0]
        self.assertEqual(suggestion["status"], "needs_review")
        self.assertNotIn("apply", suggestion)

    def test_other_countries_give_an_estimated_us_rating(self):
        self.detail = {**MOVIE_DETAIL, "release_dates": {"results": [
            {"iso_3166_1": "GB", "release_dates": [{"certification": "15", "type": 3}]},
            {"iso_3166_1": "DE", "release_dates": [{"certification": "16", "type": 3}]},
            {"iso_3166_1": "FR", "release_dates": [{"certification": "12", "type": 3}]},
        ]}}
        suggestion = self.suggest([self.movie.id]).data["results"][0]
        self.assertEqual(suggestion["status"], "estimated")
        self.assertEqual(suggestion["rating"], "R")
        self.assertIn("GB 15", suggestion["message"])
        self.assertEqual(suggestion["estimate"]["age"], 15)
        self.assertEqual(suggestion["apply"]["fields"], ["content_rating"])

        apply = self.client.post(
            f"/api/metadata-match/movie/{self.movie.id}/apply/",
            {**suggestion["apply"], "operation_id": str(uuid.uuid4())},
            format="json",
        )
        self.assertEqual(apply.status_code, 200, apply.data)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.content_rating, "R")
        change = MetadataChangeSet.objects.get(target_id=self.movie.id)
        self.assertEqual(change.details["estimated_fields"], ["content_rating"])
        self.assertIn("estimated", change.note)

    def test_unknown_foreign_ratings_give_no_estimate(self):
        self.detail = {**MOVIE_DETAIL, "release_dates": {"results": [
            {"iso_3166_1": "ZZ", "release_dates": [{"certification": "Banned", "type": 3}]},
        ]}}
        suggestion = self.suggest([self.movie.id]).data["results"][0]
        self.assertEqual(suggestion["status"], "no_rating")
        self.assertNotIn("apply", suggestion)

    def test_manually_locked_rating_is_respected(self):
        CanonicalFieldState.objects.create(
            target_type=CanonicalFieldState.TargetType.MEDIA_ITEM,
            target_id=self.movie.id,
            field_name="content_rating",
            source=CanonicalFieldState.Source.MANUAL,
            locked=True,
        )
        suggestion = self.suggest([self.movie.id]).data["results"][0]
        self.assertEqual(suggestion["status"], "locked")
        self.assertNotIn("apply", suggestion)

    def test_provider_failure_is_per_item(self):
        from integrations.providers.http import ProviderHttpError

        self.request.side_effect = ProviderHttpError("x", status=401)
        response = self.suggest([self.movie.id])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["status"], "error")
        self.assertIn("rejected", response.data["results"][0]["message"])

    def test_request_validation(self):
        theirs_library = Library.objects.create(owner=self.other, name="Theirs", path="/t", content_type="movies")
        theirs = MediaItem.objects.create(library=theirs_library, title="X", media_type=MediaItem.MediaType.MOVIE)
        other_library_movie = MediaItem.objects.create(
            library=self.tv, title="Wrong library", media_type=MediaItem.MediaType.MOVIE
        )
        self.assertEqual(self.suggest([]).status_code, 400)
        self.assertEqual(self.suggest(["not-a-uuid"]).status_code, 400)
        self.assertEqual(self.suggest([uuid.uuid4() for _ in range(11)]).status_code, 400)
        self.assertEqual(self.suggest([theirs.id]).status_code, 404)
        self.assertEqual(self.suggest([other_library_movie.id]).status_code, 404)
        self.assertEqual(self.suggest([self.movie.id], library=theirs_library).status_code, 404)
        self.request.assert_not_called()

    def test_no_connection(self):
        from integrations.models import LibraryIntegration

        LibraryIntegration.objects.filter(library=self.library).delete()
        response = self.suggest([self.movie.id])
        self.assertEqual(response.status_code, 400)
        self.assertIn("No enabled provider connection", response.data["detail"])


class _ContentTypeBase(_MatchApiTestCase):
    def setUp(self):
        super().setUp()
        from catalog.models import Channel

        self.youtube = Library.objects.create(owner=self.user, name="Youtube", path="/yt", content_type="online_video")
        self.bluey = Channel.objects.create(library=self.youtube, provider="youtube", source_id="UC1", title="Bluey")
        self.news = Channel.objects.create(
            library=self.youtube, provider="youtube", source_id="UC2", title="News", content_rating="TV-14"
        )
        self.mixed = Library.objects.create(owner=self.user, name="Mixed", path="/mixed", content_type="mixed")
        MediaItem.objects.create(library=self.mixed, title="Cars", media_type=MediaItem.MediaType.MOVIE)
        Channel.objects.create(library=self.mixed, provider="youtube", source_id="UC3", title="Clips")

    def coverage(self, library, **params):
        return self.client.get(f"/api/libraries/{library.id}/ratings/", params)


class ContentTypeTests(_ContentTypeBase):
    def test_kinds_follow_library_content(self):
        kinds = lambda library: [item["kind"] for item in self.coverage(library).data["kinds"]]
        self.assertEqual(kinds(self.youtube), ["channel"])
        self.assertEqual(kinds(self.library), ["movie"])
        self.assertEqual(kinds(self.tv), ["series"])
        self.assertEqual(kinds(self.mixed), ["movie", "channel"])
        channel = self.coverage(self.youtube).data["kinds"][0]
        self.assertFalse(channel["provider_suggestions"])
        self.assertFalse(channel["nfo"])

    def test_channel_coverage(self):
        data = self.coverage(self.youtube, kind="channel", status="all").data
        self.assertEqual(data["summary"]["channel"], {"total": 2, "rated": 1, "missing": 1, "unrecognized": 0})
        self.assertEqual([row["title"] for row in data["results"]], ["Bluey", "News"])
        self.assertIsNone(data["results"][0]["year"])

    def test_channels_get_no_provider_suggestions(self):
        response = self.client.get(
            f"/api/libraries/{self.youtube.id}/ratings/suggestions/", {"kind": "channel", "ids": str(self.bluey.id)}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("by hand", response.data["detail"])
        self.request.assert_not_called()


class ManualRatingTests(_ContentTypeBase):
    def set_rating(self, library, kind, ids, rating):
        return self.client.post(
            f"/api/libraries/{library.id}/ratings/set/",
            {"kind": kind, "ids": [str(i) for i in ids], "rating": rating},
            format="json",
        )

    def test_set_rating_on_channels_records_a_manual_lock(self):
        response = self.set_rating(self.youtube, "channel", [self.bluey.id, self.news.id], "tv-y")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data["rating"], response.data["changed"]), ("TV-Y", 2))
        self.bluey.refresh_from_db()
        self.assertEqual(self.bluey.content_rating, "TV-Y")
        state = CanonicalFieldState.objects.get(target_id=self.bluey.id, field_name="content_rating")
        self.assertEqual((state.target_type, state.source, state.locked), ("channel", "manual", True))
        change = MetadataChangeSet.objects.get(target_id=self.news.id)
        self.assertEqual(change.changes, {"content_rating": {"old": "TV-14", "new": "TV-Y"}})
        again = self.set_rating(self.youtube, "channel", [self.bluey.id], "TV-Y").data
        self.assertEqual(again["changed"], 0)

    def test_set_and_clear_movie_rating(self):
        self.assertEqual(self.set_rating(self.library, "movie", [self.movie.id], "PG").data["changed"], 1)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.content_rating, "PG")
        self.assertEqual(self.set_rating(self.library, "movie", [self.movie.id], "").data["changed"], 1)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.content_rating, "")

    def test_manual_rating_survives_nfo_import(self):
        from metadata.models import NfoFile

        self.set_rating(self.library, "movie", [self.movie.id], "PG")
        NfoFile.objects.create(
            library=self.library, media_item=self.movie, relative_path="m/m.nfo", file_name="m.nfo",
            root_element="movie", parsed_data={"movie": {"mpaa": "R"}}, parse_status=NfoFile.ParseStatus.OK,
        )
        preview = self.client.get(f"/api/libraries/{self.library.id}/ratings/nfo-import/", {"kind": "movie"}).data
        self.assertEqual(preview["summary"]["locked"], 1)

    def test_validation_and_scope(self):
        theirs = Library.objects.create(owner=self.other, name="T", path="/t", content_type="online_video")
        cases = (
            (self.youtube, "episode", [self.bluey.id], "TV-Y", 400),
            (self.youtube, "channel", [], "TV-Y", 400),
            (self.youtube, "channel", ["nope"], "TV-Y", 400),
            (self.youtube, "channel", [self.bluey.id], "x" * 65, 400),
            (self.youtube, "channel", [self.bluey.id], None, 400),
            (self.youtube, "movie", [self.bluey.id], "PG", 404),
            (self.library, "channel", [self.bluey.id], "PG", 404),
            (theirs, "channel", [self.bluey.id], "PG", 404),
        )
        for library, kind, ids, rating, status in cases:
            with self.subTest(kind=kind, rating=rating, library=library.name):
                self.assertEqual(self.set_rating(library, kind, ids, rating).status_code, status)
        self.bluey.refresh_from_db()
        self.assertEqual(self.bluey.content_rating, "")
