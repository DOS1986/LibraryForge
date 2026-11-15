"""Rating suggestions across several metadata providers, tried in order."""

import uuid
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from integrations.crypto import encrypt_secrets
from integrations.models import IntegrationConnection, LibraryIntegration
from integrations.tests.test_omdb import MOVIE as OMDB_MOVIE
from integrations.tests.test_tmdb import MOVIE_DETAIL, MOVIE_SEARCH
from metadata.test_provider_match import _MatchApiTestCase

GB_ONLY = {"results": [{"iso_3166_1": "GB", "release_dates": [{"certification": "15", "type": 3}]}]}


class ProviderChainTests(_MatchApiTestCase):
    def setUp(self):
        super().setUp()
        self.omdb = IntegrationConnection.objects.create(
            owner=self.user,
            name="My OMDb",
            provider="omdb",
            configuration={},
            encrypted_secrets=encrypt_secrets({"api_key": "abcd1234"}),
        )
        LibraryIntegration.objects.filter(library=self.library).update(priority=10)
        self.omdb_link = LibraryIntegration.objects.create(
            library=self.library, connection=self.omdb, capabilities=["metadata"], priority=20
        )
        self.tmdb_detail = MOVIE_DETAIL
        self.request.side_effect = lambda url, **kwargs: MOVIE_SEARCH if "/search/" in url else self.tmdb_detail

        omdb_patch = patch("integrations.providers.omdb.request_json")
        self.omdb_request = omdb_patch.start()
        self.addCleanup(omdb_patch.stop)
        self.omdb_request.return_value = OMDB_MOVIE

        # The fixture movie has no IDs yet, so the first provider must search.
        self.movie.external_ids = {}
        self.movie.save()

    def suggest(self, **params):
        response = self.client.get(
            f"/api/libraries/{self.library.id}/ratings/suggestions/",
            {"kind": "movie", "ids": str(self.movie.id), **params},
        )
        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        return response.data

    def omdb_params(self, index=-1):
        return parse_qs(urlparse(self.omdb_request.call_args_list[index].args[0]).query)

    def test_tmdb_rating_wins_and_omdb_is_not_called(self):
        data = self.suggest()
        result = data["results"][0]
        self.assertEqual((result["status"], result["rating"], result["provider"]), ("suggested", "R", "tmdb"))
        self.assertEqual(result["tried"], ["TMDB"])
        self.omdb_request.assert_not_called()
        self.assertEqual([item["provider"] for item in data["connections"]], ["tmdb", "omdb"])

    def test_omdb_fills_a_missing_us_rating_using_the_imdb_id_tmdb_found(self):
        self.tmdb_detail = {**MOVIE_DETAIL, "release_dates": GB_ONLY}
        result = self.suggest()["results"][0]
        self.assertEqual((result["status"], result["rating"], result["provider"]), ("suggested", "R", "omdb"))
        self.assertEqual(result["tried"], ["TMDB", "OMDb"])
        # Looked up directly by IMDb ID, never searched by title.
        self.assertEqual(self.omdb_params()["i"], ["tt0133093"])
        self.assertNotIn("s", self.omdb_params())
        self.assertEqual(result["candidate"]["match"]["reasons"][0]["code"], "external_id_lookup")
        self.assertEqual(result["apply"]["connection"], str(self.omdb.id))

        apply = self.client.post(
            f"/api/metadata-match/movie/{self.movie.id}/apply/",
            {**result["apply"], "operation_id": str(uuid.uuid4())},
            format="json",
        )
        self.assertEqual(apply.status_code, 200, apply.data)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.content_rating, "R")

    def test_estimate_is_kept_when_no_provider_has_a_us_rating(self):
        self.tmdb_detail = {**MOVIE_DETAIL, "release_dates": GB_ONLY}
        self.omdb_request.return_value = {**OMDB_MOVIE, "Rated": "N/A"}
        result = self.suggest()["results"][0]
        self.assertEqual((result["status"], result["rating"], result["provider"]), ("estimated", "R", "tmdb"))
        self.assertEqual(result["tried"], ["TMDB", "OMDb"])

    def test_known_imdb_id_skips_the_search(self):
        LibraryIntegration.objects.filter(pk=self.omdb_link.pk).update(priority=1)
        self.movie.external_ids = {"imdb": "tt0133093"}
        self.movie.save()
        result = self.suggest()["results"][0]
        self.assertEqual((result["provider"], result["rating"]), ("omdb", "R"))
        self.assertEqual(self.omdb_request.call_count, 1)
        self.request.assert_not_called()

    def test_a_chosen_connection_is_the_only_one_used(self):
        self.tmdb_detail = {**MOVIE_DETAIL, "release_dates": GB_ONLY}
        result = self.suggest(connection=str(self.connection.id))["results"][0]
        self.assertEqual((result["status"], result["tried"]), ("estimated", ["TMDB"]))
        self.omdb_request.assert_not_called()

    def test_provider_error_falls_through_to_the_next_provider(self):
        from integrations.providers.http import ProviderHttpError

        self.request.side_effect = ProviderHttpError("x", status=503)
        self.omdb_request.side_effect = [
            {"Search": [{"Title": "The Matrix", "Year": "1999", "imdbID": "tt0133093", "Type": "movie"}],
             "Response": "True"},
            OMDB_MOVIE,
            OMDB_MOVIE,
        ]
        result = self.suggest()["results"][0]
        self.assertEqual((result["status"], result["provider"]), ("suggested", "omdb"))


class TvdbChainTests(ProviderChainTests):
    """TMDB's series details include the TVDB ID, so TheTVDB is asked directly."""

    def setUp(self):
        super().setUp()
        from catalog.models import Series

        self.tvdb = IntegrationConnection.objects.create(
            owner=self.user, name="My TVDB", provider="tvdb", configuration={},
            encrypted_secrets=encrypt_secrets({"api_key": "a1b2c3d4-e5f6"}),
        )
        LibraryIntegration.objects.filter(library=self.tv).update(priority=10)
        LibraryIntegration.objects.create(library=self.tv, connection=self.tvdb, capabilities=["metadata"], priority=20)
        self.series = Series.objects.get(pk=self.series.pk)

    def test_tvdb_fills_series_rating_by_tvdb_id(self):
        from integrations.tests.test_tmdb import SERIES_DETAIL, TV_SEARCH
        from integrations.tests.test_tvdb import SERIES as TVDB_SERIES

        no_us = {**SERIES_DETAIL, "content_ratings": {"results": [{"iso_3166_1": "GB", "rating": "18"}]}}
        self.request.side_effect = lambda url, **kwargs: TV_SEARCH if "/search/" in url else no_us
        tvdb_calls = []

        def tvdb(url, **kwargs):
            tvdb_calls.append(url)
            if url.endswith("/login"):
                return {"data": {"token": "t"}}
            return {"data": TVDB_SERIES}

        with patch("integrations.providers.tvdb.request_json", side_effect=tvdb):
            response = self.client.get(
                f"/api/libraries/{self.tv.id}/ratings/suggestions/", {"kind": "series", "ids": str(self.series.id)}
            )
        result = response.data["results"][0]
        self.assertEqual((result["status"], result["rating"], result["provider"]), ("suggested", "TV-MA", "tvdb"))
        self.assertTrue(any("/series/81189/extended" in url for url in tvdb_calls))
        self.assertFalse(any("/search" in url for url in tvdb_calls))
