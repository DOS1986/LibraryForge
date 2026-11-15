"""Mocked TMDB adapter tests. No network access and no database writes."""

from email.message import Message
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

from django.core.cache import cache
from django.test import SimpleTestCase

from integrations.providers.http import ProviderHttpError, request_json
from integrations.providers.tmdb import TMDB_ATTRIBUTION, TMDbProvider
from integrations.registry import metadata_provider_classes, provider_catalog
from integrations.security import public_provider_error
from metadata.providers import (
    ArtworkKind,
    MetadataErrorCategory,
    MetadataProviderError,
    PartialDate,
)

TOKEN = "tmdb-test-token-" + "a" * 40

MOVIE_SEARCH = {
    "page": 1,
    "results": [
        {
            "id": 603,
            "title": "The Matrix",
            "original_title": "The Matrix",
            "release_date": "1999-03-30",
            "overview": "A hacker learns the truth.",
            "poster_path": "/f89U3ADr1oiB1s9GkdPOEpXUk5H.jpg",
        },
        {"id": "not-an-int", "title": "Broken"},
        {"id": 604, "title": "", "release_date": "2003-05-15"},
        {
            "id": 55931,
            "title": "The Matrix Revisited",
            "original_title": "The Matrix Revisited",
            "release_date": "2001",
            "poster_path": "../../etc/passwd",
        },
        "garbage",
    ],
    "total_pages": 1,
    "total_results": 5,
}

TV_SEARCH = {
    "page": 1,
    "results": [
        {
            "id": 1396,
            "name": "Breaking Bad",
            "original_name": "Breaking Bad",
            "first_air_date": "2008-01-20",
            "overview": "A chemistry teacher...",
            "poster_path": "/ggFHVNu6YYI5L9pCfOacjizRGt.jpg",
        },
        {
            "id": 70523,
            "name": "Dark",
            "original_name": "Dark",
            "first_air_date": "",
        },
        {"id": 90000, "name": "La Casa de Papel", "original_name": "La casa de papel", "first_air_date": "2017-05-02"},
    ],
}

MOVIE_DETAIL = {
    "id": 603,
    "title": "The Matrix",
    "original_title": "The Matrix",
    "overview": "Set in the 22nd century...",
    "tagline": "Welcome to the Real World.",
    "release_date": "1999-03-30",
    "runtime": 136,
    "imdb_id": "tt0133093",
    "genres": [{"id": 28, "name": "Action"}, {"id": 878, "name": "Science Fiction"}, {"id": 1}],
    "production_companies": [{"id": 79, "name": "Village Roadshow Pictures"}, {"id": 174, "name": "Warner Bros. Pictures"}],
    "vote_average": 8.2,
    "external_ids": {"imdb_id": "tt0133093", "wikidata_id": "Q83495", "facebook_id": "TheMatrixMovie"},
    "release_dates": {
        "results": [
            {
                "iso_3166_1": "US",
                "release_dates": [
                    {"certification": "", "type": 1, "release_date": "1999-03-24T00:00:00.000Z"},
                    {"certification": "R", "type": 3, "release_date": "1999-03-31T00:00:00.000Z"},
                ],
            },
            {"iso_3166_1": "GB", "release_dates": [{"certification": "15", "type": 3}]},
            {"iso_3166_1": "DE", "release_dates": [{"certification": "", "type": 3}]},
            {"iso_3166_1": "BAD!", "release_dates": [{"certification": "X", "type": 3}]},
        ]
    },
    "images": {
        "posters": [
            {"file_path": "/poster-en.jpg", "width": 2000, "height": 3000, "iso_639_1": "en"},
            {"file_path": "/poster-none.jpg", "width": 1000, "height": 1500, "iso_639_1": None},
            {"file_path": "https://evil.example/x.jpg", "width": 1, "height": 1},
        ],
        "backdrops": [{"file_path": "/backdrop.jpg", "width": 3840, "height": 2160, "iso_639_1": None}],
        "logos": [{"file_path": "/logo.png", "width": 0, "height": "big", "iso_639_1": "en"}],
    },
}

SERIES_DETAIL = {
    "id": 1396,
    "name": "Breaking Bad",
    "original_name": "Breaking Bad",
    "overview": "Walter White...",
    "first_air_date": "2008-01-20",
    "last_air_date": "2013-09-29",
    "status": "Ended",
    "episode_run_time": [45, 47],
    "genres": [{"id": 18, "name": "Drama"}],
    "production_companies": [{"id": 11073, "name": "Sony Pictures Television Studios"}],
    "networks": [{"id": 174, "name": "AMC"}],
    "external_ids": {"imdb_id": "tt0903747", "tvdb_id": 81189, "wikidata_id": "Q1079"},
    "content_ratings": {
        "results": [
            {"iso_3166_1": "US", "rating": "TV-MA", "descriptors": []},
            {"iso_3166_1": "GB", "rating": "18"},
            {"iso_3166_1": "US", "rating": "TV-14"},
        ]
    },
    "poster_path": "/ggFHVNu6YYI5L9pCfOacjizRGt.jpg",
}


def _http_error(status, retry_after=None):
    error = ProviderHttpError(f"Remote service returned HTTP {status}.", status=status, retry_after=retry_after)
    return error


class _TMDbTestCase(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.provider = TMDbProvider(configuration={}, secrets={"access_token": TOKEN})
        request_patch = patch("integrations.providers.tmdb.request_json")
        sleep_patch = patch("integrations.providers.tmdb.time.sleep")
        self.request = request_patch.start()
        self.sleep = sleep_patch.start()
        self.addCleanup(request_patch.stop)
        self.addCleanup(sleep_patch.stop)

    def call(self, index=-1):
        args, kwargs = self.request.call_args_list[index]
        url = urlparse(args[0])
        return url, parse_qs(url.query), kwargs


class DefinitionTests(SimpleTestCase):
    def test_registered_for_movie_and_series_metadata(self):
        self.assertIn(TMDbProvider, metadata_provider_classes("movie"))
        self.assertIn(TMDbProvider, metadata_provider_classes("series"))
        row = {item["key"]: item for item in provider_catalog()}["tmdb"]
        self.assertEqual(row["metadata_target_types"], ["movie", "series"])
        self.assertEqual(row["capabilities"], ["metadata"])
        self.assertEqual(row["credential_mode"], "user")
        self.assertIn(TMDB_ATTRIBUTION, row["description"])
        self.assertEqual([field["name"] for field in row["fields"]], ["access_token"])
        self.assertTrue(row["fields"][0]["secret"])

    def test_validate_requires_well_formed_token(self):
        with self.assertRaisesRegex(ValueError, "Missing required"):
            TMDbProvider(configuration={}, secrets={}).validate()
        for bad in ("short", TOKEN + "\r\nX-Injected: 1", "has spaces " + "a" * 30):
            with self.subTest(token=bad), self.assertRaisesRegex(ValueError, "expected format"):
                TMDbProvider(configuration={}, secrets={"access_token": bad}).validate()
        TMDbProvider(configuration={}, secrets={"access_token": TOKEN}).validate()


class TransportTests(_TMDbTestCase):
    def test_uses_bearer_header_and_keeps_token_out_of_url(self):
        self.request.return_value = MOVIE_SEARCH
        self.provider.search_metadata(target_type="movie", query="The Matrix", year=1999)
        url, params, kwargs = self.call()
        self.assertEqual((url.scheme, url.netloc, url.path), ("https", "api.themoviedb.org", "/3/search/movie"))
        self.assertEqual(kwargs["headers"], {"Authorization": f"Bearer {TOKEN}"})
        self.assertNotIn(TOKEN, url.geturl())
        self.assertEqual(params["query"], ["The Matrix"])
        self.assertEqual(params["year"], ["1999"])
        self.assertEqual(params["include_adult"], ["false"])
        self.assertEqual(params["page"], ["1"])
        self.assertNotIn("language", params)

    def test_series_search_uses_first_air_date_year(self):
        self.request.return_value = TV_SEARCH
        self.provider.search_metadata(target_type="series", query="Breaking Bad", year=2008, language="en-US")
        url, params, _ = self.call()
        self.assertEqual(url.path, "/3/search/tv")
        self.assertEqual(params["first_air_date_year"], ["2008"])
        self.assertEqual(params["language"], ["en-US"])
        self.assertNotIn("year", params)

    def test_invalid_configuration_fails_without_request(self):
        provider = TMDbProvider(configuration={}, secrets={"access_token": "nope"})
        with self.assertRaises(MetadataProviderError) as ctx:
            provider.search_metadata(target_type="movie", query="Matrix")
        self.assertEqual(ctx.exception.category, MetadataErrorCategory.INVALID_CONFIGURATION)
        self.request.assert_not_called()

    def test_results_are_cached_per_credential(self):
        self.request.return_value = MOVIE_SEARCH
        self.provider.search_metadata(target_type="movie", query="Matrix")
        self.provider.search_metadata(target_type="movie", query="Matrix")
        self.assertEqual(self.request.call_count, 1)
        other = TMDbProvider(configuration={}, secrets={"access_token": "other-token-" + "b" * 40})
        other.search_metadata(target_type="movie", query="Matrix")
        self.assertEqual(self.request.call_count, 2)
        self.provider.search_metadata(target_type="movie", query="Matrix", year=1999)
        self.assertEqual(self.request.call_count, 3)

    def test_failures_are_not_cached(self):
        self.request.side_effect = [_http_error(404), MOVIE_SEARCH]
        with self.assertRaises(MetadataProviderError):
            self.provider.search_metadata(target_type="movie", query="Matrix")
        self.assertEqual(len(self.provider.search_metadata(target_type="movie", query="Matrix")), 2)


class SearchNormalizationTests(_TMDbTestCase):
    def test_movie_search_normalizes_and_skips_malformed_results(self):
        self.request.return_value = MOVIE_SEARCH
        results = self.provider.search_metadata(target_type="movie", query="Matrix")
        self.assertEqual([item.source_id for item in results], ["603", "55931"])
        matrix, revisited = results
        self.assertEqual(matrix.title, "The Matrix")
        self.assertEqual(matrix.original_title, "")
        self.assertEqual(matrix.release_date, PartialDate(1999, 3, 30))
        self.assertEqual(matrix.artwork_url, "https://image.tmdb.org/t/p/w342/f89U3ADr1oiB1s9GkdPOEpXUk5H.jpg")
        self.assertEqual([item.to_dict() for item in matrix.external_ids], [{"namespace": "tmdb", "value": "603"}])
        self.assertEqual(revisited.release_date.precision, "year")
        self.assertEqual(revisited.artwork_url, "")

    def test_series_search_keeps_original_titles_and_missing_dates(self):
        self.request.return_value = TV_SEARCH
        results = self.provider.search_metadata(target_type="series", query="Dark")
        by_id = {item.source_id: item for item in results}
        self.assertEqual(by_id["1396"].year, 2008)
        self.assertIsNone(by_id["70523"].release_date)
        self.assertEqual(by_id["90000"].original_title, "La casa de papel")
        self.assertTrue(all(item.target_type.value == "series" for item in results))

    def test_empty_results_are_a_successful_answer(self):
        self.request.return_value = {"page": 1, "results": [], "total_pages": 0}
        self.assertEqual(self.provider.search_metadata(target_type="movie", query="zzzz"), [])

    def test_results_must_be_a_list(self):
        self.request.return_value = {"page": 1, "results": "nope"}
        with self.assertRaises(MetadataProviderError) as ctx:
            self.provider.search_metadata(target_type="movie", query="Matrix")
        self.assertEqual(ctx.exception.category, MetadataErrorCategory.MALFORMED_RESPONSE)

    def test_limit_is_respected(self):
        self.request.return_value = MOVIE_SEARCH
        self.assertEqual(len(self.provider.search_metadata(target_type="movie", query="Matrix", limit=1)), 1)


class MovieDetailTests(_TMDbTestCase):
    def setUp(self):
        super().setUp()
        self.request.return_value = MOVIE_DETAIL
        self.detail = self.provider.get_metadata(target_type="movie", source_id="603", language="en-US")

    def test_request_appends_ids_ratings_and_images(self):
        url, params, _ = self.call()
        self.assertEqual(url.path, "/3/movie/603")
        self.assertEqual(params["append_to_response"], ["external_ids,release_dates,images"])
        self.assertEqual(params["include_image_language"], ["en,null"])

    def test_scalar_fields(self):
        self.assertEqual(self.detail.title, "The Matrix")
        self.assertEqual(self.detail.original_title, "")
        self.assertEqual(self.detail.tagline, "Welcome to the Real World.")
        self.assertEqual(self.detail.release_date, PartialDate(1999, 3, 30))
        self.assertIsNone(self.detail.end_date)
        self.assertEqual(self.detail.runtime_minutes, 136)
        self.assertEqual(self.detail.genres, ("Action", "Science Fiction"))
        self.assertEqual(self.detail.studios, ("Village Roadshow Pictures", "Warner Bros. Pictures"))
        self.assertEqual(self.detail.networks, ())

    def test_certifications_prefer_theatrical_and_skip_empty(self):
        ratings = {item.territory: item.value for item in self.detail.content_ratings}
        self.assertEqual(ratings, {"US": "R", "GB": "15"})

    def test_audience_score_is_not_a_content_rating(self):
        self.assertNotIn("8.2", [item.value for item in self.detail.content_ratings])
        self.assertNotIn("vote_average", self.detail.to_dict())

    def test_external_ids(self):
        ids = {item.namespace: item.value for item in self.detail.external_ids}
        self.assertEqual(ids, {"tmdb": "603", "imdb": "tt0133093", "wikidata": "Q83495"})

    def test_artwork_candidates(self):
        artwork = [item.to_dict() for item in self.detail.artwork]
        self.assertEqual(
            artwork[0],
            {
                "url": "https://image.tmdb.org/t/p/original/poster-en.jpg",
                "kind": "poster",
                "width": 2000,
                "height": 3000,
                "language": "en",
                "thumbnail_url": "https://image.tmdb.org/t/p/w342/poster-en.jpg",
            },
        )
        self.assertIsNone(artwork[1]["language"])
        self.assertEqual([item.kind for item in self.detail.artwork], [ArtworkKind.POSTER, ArtworkKind.POSTER, ArtworkKind.BACKDROP, ArtworkKind.LOGO])
        logo = self.detail.artwork[-1]
        self.assertTrue(logo.thumbnail_url.startswith("https://image.tmdb.org/t/p/w300/"))
        self.assertIsNone(logo.width)
        self.assertIsNone(logo.height)
        self.assertTrue(all(item.url.startswith("https://image.tmdb.org/") for item in self.detail.artwork))

    def test_raw_kept_internally_but_not_serialized(self):
        self.assertEqual(self.detail.raw["id"], 603)
        self.assertNotIn("raw", self.detail.to_dict())


class SeriesDetailTests(_TMDbTestCase):
    def test_series_mapping(self):
        self.request.return_value = SERIES_DETAIL
        detail = self.provider.get_metadata(target_type="series", source_id="1396")
        _, params, _ = self.call()
        self.assertEqual(params["append_to_response"], ["external_ids,content_ratings,images"])
        self.assertEqual(detail.runtime_minutes, 45)
        self.assertEqual(detail.release_date, PartialDate(2008, 1, 20))
        self.assertEqual(detail.end_date, PartialDate(2013, 9, 29))
        self.assertEqual(detail.networks, ("AMC",))
        self.assertEqual(detail.studios, ("Sony Pictures Television Studios",))
        self.assertEqual({item.territory: item.value for item in detail.content_ratings}, {"US": "TV-MA", "GB": "18"})
        self.assertEqual(
            {item.namespace: item.value for item in detail.external_ids},
            {"tmdb": "1396", "imdb": "tt0903747", "tvdb": "81189", "wikidata": "Q1079"},
        )
        self.assertEqual([item.kind for item in detail.artwork], [ArtworkKind.POSTER])

    def test_ongoing_series_has_no_end_date(self):
        self.request.return_value = {**SERIES_DETAIL, "status": "Returning Series"}
        self.assertIsNone(self.provider.get_metadata(target_type="series", source_id="1396").end_date)

    def test_partial_and_missing_values_stay_missing(self):
        self.request.return_value = {
            "id": 1396,
            "name": "Breaking Bad",
            "first_air_date": "2008-02-31",
            "episode_run_time": [],
            "genres": "Drama",
            "networks": None,
        }
        detail = self.provider.get_metadata(target_type="series", source_id="1396")
        self.assertIsNone(detail.release_date)
        self.assertIsNone(detail.runtime_minutes)
        self.assertEqual(detail.genres, ())
        self.assertEqual(detail.networks, ())
        self.assertEqual(detail.content_ratings, ())


class DetailValidationTests(_TMDbTestCase):
    def test_non_numeric_ids_fail_before_request(self):
        for source_id in ("abc", "0", "603.5", "-1"):
            with self.subTest(source_id=source_id), self.assertRaises(MetadataProviderError) as ctx:
                self.provider.get_metadata(target_type="movie", source_id=source_id)
            self.assertEqual(ctx.exception.category, MetadataErrorCategory.INVALID_REQUEST)
        self.request.assert_not_called()

    def test_mismatched_record_is_rejected(self):
        self.request.return_value = {**MOVIE_DETAIL, "id": 604}
        with self.assertRaises(MetadataProviderError) as ctx:
            self.provider.get_metadata(target_type="movie", source_id="603")
        self.assertEqual(ctx.exception.category, MetadataErrorCategory.MALFORMED_RESPONSE)

    def test_missing_title_is_malformed(self):
        self.request.return_value = {"id": 603, "title": ""}
        with self.assertRaises(MetadataProviderError) as ctx:
            self.provider.get_metadata(target_type="movie", source_id="603")
        self.assertEqual(ctx.exception.category, MetadataErrorCategory.MALFORMED_RESPONSE)

    def test_page_beyond_tmdb_limit_returns_empty_without_request(self):
        result = self.provider._search_metadata(
            target_type=self.provider._require_metadata_target("movie"),
            query="Matrix",
            year=None,
            language=None,
            page=501,
            limit=20,
        )
        self.assertEqual(result, [])
        self.request.assert_not_called()


class ErrorMappingTests(_TMDbTestCase):
    def assertCategory(self, side_effect, category, *, calls=1):
        self.request.reset_mock()
        self.request.side_effect = side_effect
        with self.assertRaises(MetadataProviderError) as ctx:
            self.provider.get_metadata(target_type="movie", source_id="603")
        self.assertEqual(ctx.exception.category, category)
        self.assertEqual(self.request.call_count, calls)
        self.assertNotIn(TOKEN, ctx.exception.message)
        return ctx.exception

    def test_credentials_and_missing_records_are_not_retried(self):
        self.assertCategory(_http_error(401), MetadataErrorCategory.INVALID_CREDENTIALS)
        self.assertCategory(_http_error(404), MetadataErrorCategory.NOT_FOUND)
        self.assertCategory(_http_error(400), MetadataErrorCategory.INVALID_REQUEST)
        self.sleep.assert_not_called()

    def test_short_rate_limit_is_retried_once(self):
        self.request.side_effect = [_http_error(429, retry_after=1), MOVIE_DETAIL]
        self.assertEqual(self.provider.get_metadata(target_type="movie", source_id="603").title, "The Matrix")
        self.sleep.assert_called_once_with(1.0)

    def test_long_rate_limit_is_reported_not_waited(self):
        error = self.assertCategory(_http_error(429, retry_after=30), MetadataErrorCategory.RATE_LIMITED)
        self.assertEqual(error.retry_after_seconds, 30)
        self.assertTrue(error.retryable)
        self.sleep.assert_not_called()

    def test_transient_failures_retry_with_a_cap(self):
        self.assertCategory([_http_error(503), _http_error(503)], MetadataErrorCategory.UNAVAILABLE, calls=2)
        self.assertCategory(
            [ProviderHttpError("t", reason="timeout")] * 2, MetadataErrorCategory.TIMEOUT, calls=2
        )
        self.assertCategory(
            [ProviderHttpError("u", reason="unreachable")] * 2, MetadataErrorCategory.UNAVAILABLE, calls=2
        )
        for wait in [call.args[0] for call in self.sleep.call_args_list]:
            self.assertLessEqual(wait, 1.0)

    def test_unreadable_responses(self):
        self.assertCategory(ProviderHttpError("j", reason="invalid_json"), MetadataErrorCategory.MALFORMED_RESPONSE)
        self.assertCategory(ProviderHttpError("l", reason="too_large"), MetadataErrorCategory.MALFORMED_RESPONSE)
        self.assertCategory([["not", "a", "dict"]], MetadataErrorCategory.MALFORMED_RESPONSE)

    def test_http_200_error_payloads(self):
        self.assertCategory([{"success": False, "status_code": 34}], MetadataErrorCategory.NOT_FOUND)
        self.assertCategory([{"success": False, "status_code": 11}], MetadataErrorCategory.MALFORMED_RESPONSE)


class ConnectionTestTests(_TMDbTestCase):
    def test_connection_uses_configuration_endpoint(self):
        self.request.return_value = {"images": {"poster_sizes": ["w92", "original"]}}
        result = self.provider.test_connection()
        url, _, _ = self.call()
        self.assertEqual(url.path, "/3/configuration")
        self.assertTrue(result["ok"])
        self.assertEqual(result["details"]["attribution"], TMDB_ATTRIBUTION)

    def test_connection_failure_message_is_public_and_secret_free(self):
        self.request.side_effect = _http_error(401)
        with self.assertRaises(MetadataProviderError) as ctx:
            self.provider.test_connection()
        message = public_provider_error(ctx.exception)
        self.assertEqual(message, "TMDB rejected the API Read Access Token.")
        self.assertNotIn(TOKEN, message)


class HttpHelperTests(SimpleTestCase):
    """Additive ProviderHttpError details used by adapters."""

    def _opener(self, error):
        class _Opener:
            def open(self, request, timeout):
                raise error

        return patch("integrations.providers.http.build_opener", return_value=_Opener())

    def test_http_error_carries_status_and_retry_after(self):
        headers = Message()
        headers["Retry-After"] = "7"
        with (
            self._opener(HTTPError("https://api.example/x", 429, "Too Many", headers, None)),
            self.assertRaises(ProviderHttpError) as ctx,
        ):
            request_json("https://api.example/x")
        self.assertEqual((ctx.exception.status, ctx.exception.retry_after, ctx.exception.reason), (429, 7, "http"))

    def test_http_date_retry_after_is_ignored(self):
        headers = Message()
        headers["Retry-After"] = "Wed, 21 Oct 2026 07:28:00 GMT"
        with (
            self._opener(HTTPError("https://api.example/x", 429, "Too Many", headers, None)),
            self.assertRaises(ProviderHttpError) as ctx,
        ):
            request_json("https://api.example/x")
        self.assertIsNone(ctx.exception.retry_after)

    def test_timeouts_are_distinguished(self):
        with self._opener(URLError(TimeoutError("timed out"))), self.assertRaises(ProviderHttpError) as ctx:
            request_json("https://api.example/x")
        self.assertEqual(ctx.exception.reason, "timeout")
        with self._opener(URLError(ConnectionRefusedError())), self.assertRaises(ProviderHttpError) as ctx:
            request_json("https://api.example/x")
        self.assertEqual(ctx.exception.reason, "unreachable")
        self.assertEqual(public_provider_error(ctx.exception), "Provider request failed because the remote service was unavailable.")
