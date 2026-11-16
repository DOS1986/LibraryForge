"""Mocked OMDb adapter tests. No network access."""

from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.core.cache import cache
from django.test import SimpleTestCase

from integrations.providers.http import ProviderHttpError
from integrations.providers.omdb import OMDB_ATTRIBUTION, OMDbProvider
from integrations.registry import provider_catalog
from integrations.security import public_provider_error
from metadata.providers import MetadataErrorCategory, MetadataProviderError, PartialDate

KEY = "abcd1234"

SEARCH = {
    "Search": [
        {"Title": "The Matrix", "Year": "1999", "imdbID": "tt0133093", "Type": "movie",
         "Poster": "https://m.media-amazon.com/images/M/matrix.jpg"},
        {"Title": "The Matrix Reloaded", "Year": "2003", "imdbID": "tt0234215", "Type": "movie", "Poster": "N/A"},
        {"Title": "", "Year": "2001", "imdbID": "tt0000001"},
        {"Title": "Bad id", "Year": "2001", "imdbID": "nm0000206"},
        "junk",
    ],
    "totalResults": "4",
    "Response": "True",
}

MOVIE = {
    "Title": "The Matrix", "Year": "1999", "Rated": "R", "Released": "31 Mar 1999", "Runtime": "136 min",
    "Genre": "Action, Sci-Fi", "Plot": "A computer hacker learns the truth.", "Poster": "https://m.media-amazon.com/x.jpg",
    "imdbID": "tt0133093", "Type": "movie", "Production": "N/A", "imdbRating": "8.7", "Response": "True",
}

SERIES = {
    "Title": "Bluey", "Year": "2018–", "Rated": "TV-Y", "Released": "01 Oct 2018", "Runtime": "7 min",
    "Genre": "Animation, Comedy, Family", "Plot": "Bluey is an energetic puppy.", "Poster": "N/A",
    "imdbID": "tt7678620", "Type": "series", "totalSeasons": "3", "Response": "True",
}


class _OmdbTestCase(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.provider = OMDbProvider(configuration={}, secrets={"api_key": KEY})
        request_patch = patch("integrations.providers.omdb.request_json")
        sleep_patch = patch("integrations.providers.omdb.time.sleep")
        self.request = request_patch.start()
        self.sleep = sleep_patch.start()
        self.addCleanup(request_patch.stop)
        self.addCleanup(sleep_patch.stop)

    def params(self, index=-1):
        url = urlparse(self.request.call_args_list[index].args[0])
        return url, parse_qs(url.query)


class DefinitionTests(SimpleTestCase):
    def test_catalog_entry(self):
        row = {item["key"]: item for item in provider_catalog()}["omdb"]
        self.assertEqual(row["metadata_target_types"], ["movie", "series"])
        self.assertEqual(row["metadata_id_namespace"], "imdb")
        self.assertEqual(row["attribution"], OMDB_ATTRIBUTION)
        self.assertIn("non-commercial", row["credential_summary"])
        self.assertTrue(row["fields"][0]["secret"])

    def test_key_validation(self):
        with self.assertRaisesRegex(ValueError, "Missing required"):
            OMDbProvider(configuration={}, secrets={}).validate()
        with self.assertRaisesRegex(ValueError, "expected format"):
            OMDbProvider(configuration={}, secrets={"api_key": "bad key!"}).validate()


class SearchTests(_OmdbTestCase):
    def test_search_request_and_normalization(self):
        self.request.return_value = SEARCH
        results = self.provider.search_metadata(target_type="movie", query="The Matrix", year=1999)
        url, params = self.params()
        self.assertEqual((url.scheme, url.netloc), ("https", "www.omdbapi.com"))
        self.assertEqual(params["s"], ["The Matrix"])
        self.assertEqual(params["type"], ["movie"])
        self.assertEqual(params["y"], ["1999"])
        self.assertEqual(params["apikey"], [KEY])
        self.assertEqual([item.source_id for item in results], ["tt0133093", "tt0234215"])
        self.assertEqual(results[0].artwork_url, "https://m.media-amazon.com/images/M/matrix.jpg")
        self.assertEqual(results[1].artwork_url, "")
        self.assertEqual(results[0].release_date, PartialDate(1999))
        self.assertEqual(results[0].external_ids[0].to_dict(), {"namespace": "imdb", "value": "tt0133093"})

    def test_series_search_type_and_not_found_is_empty(self):
        self.request.return_value = {"Response": "False", "Error": "Series not found!"}
        self.assertEqual(self.provider.search_metadata(target_type="series", query="Nope"), [])
        self.assertEqual(self.params()[1]["type"], ["series"])

    def test_too_many_results(self):
        self.request.return_value = {"Response": "False", "Error": "Too many results."}
        with self.assertRaises(MetadataProviderError) as ctx:
            self.provider.search_metadata(target_type="movie", query="a")
        self.assertEqual(ctx.exception.category, MetadataErrorCategory.INVALID_REQUEST)


class DetailTests(_OmdbTestCase):
    def test_movie_details(self):
        self.request.return_value = MOVIE
        detail = self.provider.get_metadata(target_type="movie", source_id="tt0133093")
        self.assertEqual(self.params()[1]["i"], ["tt0133093"])
        self.assertEqual(self.params()[1]["plot"], ["full"])
        self.assertEqual(detail.title, "The Matrix")
        self.assertEqual(detail.release_date, PartialDate(1999, 3, 31))
        self.assertEqual(detail.runtime_minutes, 136)
        self.assertEqual([item.to_dict() for item in detail.content_ratings], [{"value": "R", "territory": "US"}])
        self.assertEqual(detail.genres, ("Action", "Sci-Fi"))
        self.assertEqual(detail.studios, ())
        self.assertEqual(len(detail.artwork), 1)
        self.assertNotIn("8.7", [item.value for item in detail.content_ratings])

    def test_series_details_and_year_ranges(self):
        self.request.return_value = SERIES
        detail = self.provider.get_metadata(target_type="series", source_id="tt7678620")
        self.assertEqual(detail.content_ratings[0].value, "TV-Y")
        self.assertIsNone(detail.end_date)
        self.assertEqual(detail.artwork, ())
        cache.clear()
        self.request.return_value = {**SERIES, "Year": "2008–2013", "imdbID": "tt0903747"}
        ended = self.provider.get_metadata(target_type="series", source_id="tt0903747")
        self.assertEqual(ended.end_date, PartialDate(2013))

    def test_regional_release_date_falls_back_to_year(self):
        self.request.return_value = {**MOVIE, "Released": "12 Jun 2001"}
        detail = self.provider.get_metadata(target_type="movie", source_id="tt0133093")
        self.assertEqual(detail.release_date, PartialDate(1999))

    def test_missing_values_and_type_mismatch(self):
        self.request.return_value = {**MOVIE, "Rated": "N/A", "Runtime": "N/A", "Genre": "N/A", "Released": "N/A"}
        detail = self.provider.get_metadata(target_type="movie", source_id="tt0133093")
        self.assertEqual((detail.content_ratings, detail.runtime_minutes, detail.genres), ((), None, ()))
        self.assertEqual(detail.release_date, PartialDate(1999))
        cache.clear()
        self.request.return_value = SERIES
        with self.assertRaises(MetadataProviderError) as ctx:
            self.provider.get_metadata(target_type="movie", source_id="tt7678620")
        self.assertEqual(ctx.exception.category, MetadataErrorCategory.NOT_FOUND)

    def test_invalid_ids_fail_before_request(self):
        for source_id in ("603", "nm0000206", "tt12"):
            with self.subTest(source_id=source_id), self.assertRaises(MetadataProviderError):
                self.provider.get_metadata(target_type="movie", source_id=source_id)
        self.request.assert_not_called()

    def test_mismatched_record_is_rejected(self):
        self.request.return_value = {**MOVIE, "imdbID": "tt0234215"}
        with self.assertRaises(MetadataProviderError) as ctx:
            self.provider.get_metadata(target_type="movie", source_id="tt0133093")
        self.assertEqual(ctx.exception.category, MetadataErrorCategory.MALFORMED_RESPONSE)


class ErrorTests(_OmdbTestCase):
    def category(self, side_effect):
        cache.clear()
        self.request.reset_mock()
        self.request.side_effect = side_effect
        with self.assertRaises(MetadataProviderError) as ctx:
            self.provider.get_metadata(target_type="movie", source_id="tt0133093")
        self.assertNotIn(KEY, ctx.exception.message)
        return ctx.exception.category

    def test_error_messages_and_statuses(self):
        cases = [
            ([{"Response": "False", "Error": "Incorrect IMDb ID."}], MetadataErrorCategory.NOT_FOUND),
            ([{"Response": "False", "Error": "Invalid API key!"}], MetadataErrorCategory.INVALID_CREDENTIALS),
            ([{"Response": "False", "Error": "Request limit reached!"}], MetadataErrorCategory.RATE_LIMITED),
            ([{"Response": "False", "Error": "Something odd"}], MetadataErrorCategory.MALFORMED_RESPONSE),
            ([ProviderHttpError("x", status=401)], MetadataErrorCategory.INVALID_CREDENTIALS),
            ([ProviderHttpError("x", status=503)] * 2, MetadataErrorCategory.UNAVAILABLE),
            ([ProviderHttpError("x", reason="timeout")] * 2, MetadataErrorCategory.TIMEOUT),
            ([["not", "a", "dict"]], MetadataErrorCategory.MALFORMED_RESPONSE),
        ]
        for side_effect, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(self.category(side_effect), expected)

    def test_daily_limit_is_not_retried(self):
        self.category([ProviderHttpError("x", status=429), MOVIE])
        self.assertEqual(self.request.call_count, 1)
        self.sleep.assert_not_called()

    def test_connection_test(self):
        self.request.return_value = MOVIE
        self.assertTrue(self.provider.test_connection()["ok"])
        self.assertEqual(self.params()[1]["i"], ["tt0133093"])
        self.request.return_value = {"Response": "False", "Error": "Invalid API key!"}
        cache.clear()
        with self.assertRaises(MetadataProviderError) as ctx:
            self.provider.test_connection()
        self.assertEqual(public_provider_error(ctx.exception), "OMDb rejected the API key.")

    def test_results_are_cached_per_key(self):
        self.request.return_value = MOVIE
        self.provider.get_metadata(target_type="movie", source_id="tt0133093")
        self.provider.get_metadata(target_type="movie", source_id="tt0133093")
        self.assertEqual(self.request.call_count, 1)
        OMDbProvider(configuration={}, secrets={"api_key": "zzzz9999"}).get_metadata(
            target_type="movie", source_id="tt0133093"
        )
        self.assertEqual(self.request.call_count, 2)
