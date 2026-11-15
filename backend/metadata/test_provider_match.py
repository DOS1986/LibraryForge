"""API tests for read-only metadata matching (search and preview).

TMDB is mocked at the transport. These tests also prove that search and
preview never change catalog metadata, provenance, or history.
"""

import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase

from catalog.models import CanonicalFieldState, MetadataChangeSet, Series
from integrations.crypto import encrypt_secrets
from integrations.models import IntegrationConnection, LibraryIntegration
from integrations.providers.http import ProviderHttpError
from integrations.tests.test_tmdb import (
    MOVIE_DETAIL,
    MOVIE_SEARCH,
    SERIES_DETAIL,
    TOKEN,
    TV_SEARCH,
)
from libraries.models import Library
from media.models import MediaItem


class _MatchApiTestCase(APITestCase):
    def setUp(self):
        cache.clear()
        user_model = get_user_model()
        self.user = user_model.objects.create_user(email="owner@example.com", password="password")
        self.other = user_model.objects.create_user(email="other@example.com", password="password")
        self.client.force_authenticate(self.user)

        self.library = Library.objects.create(owner=self.user, name="Movies", path="/movies", content_type="movies")
        self.tv = Library.objects.create(owner=self.user, name="TV", path="/tv", content_type="tv")
        self.movie = MediaItem.objects.create(
            library=self.library,
            title="The Matrix",
            media_type=MediaItem.MediaType.MOVIE,
            canonical_metadata={"semantic": {"kind": "movie", "year": 1999}},
            genres=["Action"],
            external_ids={"imdb": "tt0133093"},
        )
        self.series = Series.objects.create(library=self.tv, title="Breaking Bad", semantic_key="breaking-bad", start_year=2008)

        self.connection = self._connection(self.user, "My TMDB")
        for library in (self.library, self.tv):
            LibraryIntegration.objects.create(library=library, connection=self.connection, capabilities=["metadata"])

        request_patch = patch("integrations.providers.tmdb.request_json")
        sleep_patch = patch("integrations.providers.tmdb.time.sleep")
        self.request = request_patch.start()
        sleep_patch.start()
        self.addCleanup(request_patch.stop)
        self.addCleanup(sleep_patch.stop)

    @staticmethod
    def _connection(owner, name, provider="tmdb", enabled=True):
        secrets = {"access_token": TOKEN} if provider == "tmdb" else {"api_key": "youtube-key"}
        return IntegrationConnection.objects.create(
            owner=owner,
            name=name,
            provider=provider,
            enabled=enabled,
            configuration={},
            encrypted_secrets=encrypt_secrets(secrets),
        )

    def url(self, kind, target_id, action=""):
        return f"/api/metadata-match/{kind}/{target_id}/" + (f"{action}/" if action else "")

    def catalog_snapshot(self):
        self.movie.refresh_from_db()
        self.series.refresh_from_db()
        return (
            {field.name: getattr(self.movie, field.name) for field in MediaItem._meta.fields},
            {field.name: getattr(self.series, field.name) for field in Series._meta.fields},
            CanonicalFieldState.objects.count(),
            MetadataChangeSet.objects.count(),
        )


class ContextTests(_MatchApiTestCase):
    def test_context_lists_eligible_connections_and_defaults(self):
        youtube = self._connection(self.user, "YouTube", provider="youtube")
        LibraryIntegration.objects.create(library=self.library, connection=youtube, capabilities=["metadata"])
        response = self.client.get(self.url("movie", self.movie.id))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["target"]["title"], "The Matrix")
        self.assertEqual(response.data["search_defaults"], {"query": "The Matrix", "year": 1999, "original_title": ""})
        rows = {row["provider"]: row for row in response.data["connections"]}
        self.assertTrue(rows["tmdb"]["available"])
        self.assertIn("not endorsed", rows["tmdb"]["attribution"])
        self.assertFalse(rows["youtube"]["available"])
        self.assertIn("does not provide movie metadata", rows["youtube"]["reason"])
        self.request.assert_not_called()

    def test_targets_are_owner_scoped_and_type_checked(self):
        other_library = Library.objects.create(owner=self.other, name="Theirs", path="/theirs", content_type="movies")
        theirs = MediaItem.objects.create(library=other_library, title="Theirs", media_type=MediaItem.MediaType.MOVIE)
        episode_like = MediaItem.objects.create(
            library=self.library, title="Pilot", media_type=MediaItem.MediaType.TV_EPISODE
        )
        for url in (
            self.url("movie", theirs.id),
            self.url("movie", theirs.id, "search"),
            self.url("movie", theirs.id, "preview") + "?source_id=603",
            self.url("movie", episode_like.id),
            self.url("series", self.movie.id),
            self.url("episode", self.movie.id),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)
        self.request.assert_not_called()

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url("movie", self.movie.id)).status_code, (401, 403))


class SearchTests(_MatchApiTestCase):
    def test_search_returns_candidates_with_hints(self):
        self.request.return_value = MOVIE_SEARCH
        response = self.client.get(self.url("movie", self.movie.id, "search"), {"year": "1999"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["query"], "The Matrix")
        self.assertEqual(response.data["connection"]["connection_id"], str(self.connection.id))
        first = response.data["results"][0]
        self.assertEqual((first["source_id"], first["target_type"], first["year"]), ("603", "movie", 1999))
        self.assertEqual(first["match"]["tier"], "likely")
        self.assertIsNone(response.data["next_page"])

    def test_search_query_override(self):
        self.request.return_value = TV_SEARCH
        response = self.client.get(self.url("series", self.series.id, "search"), {"query": "Breaking  Bad", "page": "2"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["page"], 2)
        self.assertEqual(response.data["results"][0]["target_type"], "series")

    def test_connection_must_be_assigned_owned_and_enabled(self):
        theirs = self._connection(self.other, "Their TMDB")
        unassigned = self._connection(self.user, "Unassigned TMDB")
        disabled = self._connection(self.user, "Disabled TMDB", enabled=False)
        LibraryIntegration.objects.create(library=self.library, connection=disabled, capabilities=["metadata"])
        artwork_only = self._connection(self.user, "Artwork-only link")
        LibraryIntegration.objects.create(library=self.library, connection=artwork_only, capabilities=["artwork"])
        for connection in (theirs, unassigned, disabled, artwork_only):
            with self.subTest(connection=connection.name):
                response = self.client.get(self.url("movie", self.movie.id, "search"), {"connection": str(connection.id)})
                self.assertEqual(response.status_code, 400)
                self.assertIn("Choose a provider connection", response.data["detail"])
        self.request.assert_not_called()

    def test_ambiguous_or_missing_connection(self):
        second = self._connection(self.user, "Second TMDB")
        LibraryIntegration.objects.create(library=self.library, connection=second, capabilities=["metadata"])
        response = self.client.get(self.url("movie", self.movie.id, "search"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Choose which provider connection to use.")
        LibraryIntegration.objects.filter(library=self.library).delete()
        response = self.client.get(self.url("movie", self.movie.id, "search"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("No enabled provider connection", response.data["detail"])

    def test_invalid_input(self):
        response = self.client.get(self.url("movie", self.movie.id, "search"), {"year": "nineteen"})
        self.assertEqual(response.status_code, 400)
        response = self.client.get(self.url("movie", self.movie.id, "search"), {"query": "  "})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["category"], "invalid_request")
        self.request.assert_not_called()

    def test_provider_failures_map_to_statuses(self):
        cases = (
            (ProviderHttpError("x", status=401), 502, "invalid_credentials"),
            (ProviderHttpError("x", status=429, retry_after=30), 429, "rate_limited"),
            (ProviderHttpError("x", reason="timeout"), 504, "timeout"),
        )
        for error, status, category in cases:
            with self.subTest(category=category):
                cache.clear()
                self.request.reset_mock()
                self.request.side_effect = [error, error]
                response = self.client.get(self.url("movie", self.movie.id, "search"))
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.data["error"]["category"], category)
                self.assertNotIn(TOKEN, str(response.data))
        self.assertEqual(response.status_code, 504)
        self.request.side_effect = [ProviderHttpError("x", status=429, retry_after=30)]
        cache.clear()
        response = self.client.get(self.url("movie", self.movie.id, "search"))
        self.assertEqual(response["Retry-After"], "30")

    def test_empty_results_are_success(self):
        self.request.return_value = {"page": 1, "results": []}
        response = self.client.get(self.url("movie", self.movie.id, "search"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])


class PreviewTests(_MatchApiTestCase):
    def preview(self, kind="movie", target=None, **params):
        target = target or (self.movie if kind == "movie" else self.series)
        response = self.client.get(self.url(kind, target.id, "preview"), {"source_id": "603" if kind == "movie" else "1396", **params})
        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        return response.data, {row["field"]: row for row in response.data["fields"]}

    def test_movie_preview_defaults_retain_existing_values(self):
        self.movie.release_date = datetime.date(1999, 3, 31)
        self.movie.description = "My own description."
        self.movie.save()
        self.request.return_value = MOVIE_DETAIL
        data, rows = self.preview()

        self.assertEqual(rows["title"]["status"], "unchanged")
        self.assertEqual(rows["release_date"]["status"], "different")
        self.assertFalse(rows["release_date"]["default_selected"])
        self.assertTrue(rows["release_date"]["selectable"])
        self.assertEqual(rows["year"]["status"], "unchanged")
        self.assertEqual(rows["description"]["current"], "My own description.")
        self.assertEqual(rows["description"]["status"], "different")
        self.assertFalse(rows["description"]["default_selected"])

        self.assertEqual(rows["tagline"]["status"], "fill")
        self.assertTrue(rows["tagline"]["default_selected"])
        self.assertEqual(rows["sort_title"]["status"], "missing")
        self.assertFalse(rows["sort_title"]["selectable"])

        self.assertEqual(rows["genres"]["status"], "add")
        self.assertEqual(rows["genres"]["additions"], ["Science Fiction"])
        self.assertEqual(rows["genres"]["result"], ["Action", "Science Fiction"])
        self.assertFalse(rows["genres"]["default_selected"])
        self.assertEqual(rows["studios"]["status"], "fill")
        self.assertTrue(rows["studios"]["default_selected"])

        self.assertEqual(rows["content_rating"]["proposed"], "R")
        self.assertEqual(rows["content_rating"]["territory"], "US")
        self.assertEqual(rows["external_ids.imdb"]["status"], "unchanged")
        self.assertEqual(rows["external_ids.tmdb"]["status"], "fill")
        self.assertEqual(rows["external_ids.wikidata"]["status"], "fill")

        self.assertEqual(data["not_stored"][0]["label"], "Runtime")
        self.assertNotIn("raw", data["provider_metadata"])
        self.assertEqual(len(data["target_revision"]), 64)
        self.assertEqual(len(data["provider_snapshot"]), 64)
        self.assertGreater(data["summary"]["fill"], 0)

    def test_release_date_links_year(self):
        self.movie.canonical_metadata = {"semantic": {"kind": "movie", "year": 2003}}
        self.movie.save()
        self.request.return_value = MOVIE_DETAIL
        _, rows = self.preview()
        self.assertEqual(rows["release_date"]["linked_fields"], ["year"])
        self.assertIn("Also sets the year to 1999", rows["release_date"]["note"])
        self.assertEqual(rows["year"]["linked_to"], "release_date")

    def test_partial_provider_date_is_not_offered_as_full_date(self):
        self.request.return_value = {**MOVIE_DETAIL, "release_date": "1999"}
        _, rows = self.preview()
        self.assertEqual(rows["release_date"]["status"], "missing")
        self.assertIn("partial date", rows["release_date"]["note"])

    def test_locked_fields_cannot_be_selected(self):
        CanonicalFieldState.objects.create(
            target_type=CanonicalFieldState.TargetType.MEDIA_ITEM,
            target_id=self.movie.id,
            field_name="tagline",
            source=CanonicalFieldState.Source.MANUAL,
            locked=True,
        )
        CanonicalFieldState.objects.create(
            target_type=CanonicalFieldState.TargetType.MEDIA_ITEM,
            target_id=self.movie.id,
            field_name="genres",
            source=CanonicalFieldState.Source.MANUAL,
            locked=True,
        )
        self.request.return_value = MOVIE_DETAIL
        _, rows = self.preview()
        for field in ("tagline", "genres"):
            self.assertEqual(rows[field]["status"], "locked")
            self.assertFalse(rows[field]["selectable"])
            self.assertFalse(rows[field]["default_selected"])
            self.assertEqual(rows[field]["current_source"], "manual")

    def test_conflicting_external_id_is_never_offered(self):
        self.movie.external_ids = {"imdb": "tt9999999"}
        self.movie.save()
        self.request.return_value = MOVIE_DETAIL
        _, rows = self.preview()
        self.assertEqual(rows["external_ids.imdb"]["status"], "conflict")
        self.assertFalse(rows["external_ids.imdb"]["selectable"])

    def test_missing_us_rating_is_estimated_but_not_preselected(self):
        self.request.return_value = {**MOVIE_DETAIL, "release_dates": {"results": [
            {"iso_3166_1": "GB", "release_dates": [{"certification": "PG", "type": 3}]},
        ]}}
        _, rows = self.preview()
        row = rows["content_rating"]
        self.assertEqual((row["proposed"], row["status"]), ("PG", "fill"))
        self.assertTrue(row["estimated"])
        self.assertTrue(row["selectable"])
        self.assertFalse(row["default_selected"])
        self.assertIn("GB PG", row["note"])

    def test_territory_selection(self):
        self.request.return_value = MOVIE_DETAIL
        _, rows = self.preview(territory="gb")
        self.assertEqual(rows["content_rating"]["proposed"], "15")
        _, rows = self.preview(territory="FR")
        self.assertEqual(rows["content_rating"]["status"], "missing")
        self.assertIn("Other countries", rows["content_rating"]["note"])
        _, rows = self.preview(language="en-GB")
        self.assertEqual(rows["content_rating"]["territory"], "GB")
        response = self.client.get(self.url("movie", self.movie.id, "preview"), {"source_id": "603", "territory": "USA"})
        self.assertEqual(response.status_code, 400)

    def test_series_preview(self):
        self.request.return_value = SERIES_DETAIL
        data, rows = self.preview(kind="series")
        self.assertEqual(rows["start_year"]["status"], "unchanged")
        self.assertEqual(rows["end_year"]["status"], "fill")
        self.assertEqual(rows["end_year"]["proposed"], 2013)
        self.assertEqual(rows["studios"]["proposed"], ["Sony Pictures Television Studios"])
        self.assertEqual(rows["external_ids.tvdb"]["proposed"], "81189")
        self.assertNotIn("release_date", rows)
        labels = {row["label"] for row in data["not_stored"]}
        self.assertEqual(labels, {"Episode runtime", "Networks"})

    def test_preview_requires_candidate_and_maps_missing_record(self):
        response = self.client.get(self.url("movie", self.movie.id, "preview"))
        self.assertEqual(response.status_code, 400)
        self.request.side_effect = ProviderHttpError("x", status=404)
        response = self.client.get(self.url("movie", self.movie.id, "preview"), {"source_id": "603"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"]["category"], "not_found")


class NoWriteTests(_MatchApiTestCase):
    def test_search_and_preview_never_change_catalog(self):
        before = self.catalog_snapshot()
        self.request.side_effect = lambda url, **kwargs: (
            MOVIE_SEARCH if "/search/movie" in url
            else TV_SEARCH if "/search/tv" in url
            else MOVIE_DETAIL if "/movie/" in url
            else SERIES_DETAIL
        )
        for url, params in (
            (self.url("movie", self.movie.id), {}),
            (self.url("movie", self.movie.id, "search"), {}),
            (self.url("movie", self.movie.id, "preview"), {"source_id": "603"}),
            (self.url("series", self.series.id, "search"), {}),
            (self.url("series", self.series.id, "preview"), {"source_id": "1396"}),
        ):
            self.assertEqual(self.client.get(url, params).status_code, 200)
        self.request.side_effect = ProviderHttpError("x", status=500)
        cache.clear()
        self.client.get(self.url("movie", self.movie.id, "preview"), {"source_id": "603"})
        self.assertEqual(self.catalog_snapshot(), before)

    def test_write_methods_are_not_allowed(self):
        for method in ("post", "put", "patch", "delete"):
            for action in ("", "search", "preview"):
                with self.subTest(method=method, action=action):
                    response = getattr(self.client, method)(self.url("movie", self.movie.id, action), {})
                    self.assertEqual(response.status_code, 405)


class ThrottleTests(_MatchApiTestCase):
    def test_provider_requests_are_rate_limited_per_user(self):
        from rest_framework.settings import api_settings

        self.request.return_value = MOVIE_SEARCH
        rates = {**api_settings.DEFAULT_THROTTLE_RATES, "metadata_provider": "2/min"}
        with patch("rest_framework.throttling.SimpleRateThrottle.THROTTLE_RATES", rates):
            statuses = [self.client.get(self.url("movie", self.movie.id, "search")).status_code for _ in range(3)]
        self.assertEqual(statuses, [200, 200, 429])
