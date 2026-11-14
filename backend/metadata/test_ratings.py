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

    def test_no_rating_in_territory(self):
        self.detail = {**MOVIE_DETAIL, "release_dates": {"results": [{"iso_3166_1": "GB", "release_dates": [{"certification": "15", "type": 3}]}]}}
        suggestion = self.suggest([self.movie.id]).data["results"][0]
        self.assertEqual(suggestion["status"], "no_rating")
        self.assertIn("GB 15", suggestion["message"])
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
