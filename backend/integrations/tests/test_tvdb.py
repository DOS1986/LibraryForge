"""Mocked TheTVDB adapter tests. No network access."""

from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.core.cache import cache
from django.test import SimpleTestCase

from integrations.providers.http import ProviderHttpError
from integrations.providers.tvdb import TVDB_ATTRIBUTION, TheTVDBProvider
from integrations.registry import provider_catalog
from metadata.providers import MetadataErrorCategory, MetadataProviderError, PartialDate

KEY = "a1b2c3d4-e5f6-7890"

SEARCH = [
    {
        "tvdb_id": "81189", "name": "Breaking Bad", "year": "2008", "first_air_time": "2008-01-20",
        "overview": "Walter...", "image_url": "https://artworks.thetvdb.com/banners/posters/81189-1.jpg",
        "translations": {"eng": "Breaking Bad"},
        "remote_ids": [{"id": "tt0903747", "type": 2, "sourceName": "IMDB"}],
    },
    {"tvdb_id": "362696", "name": "La casa de papel", "year": "2017", "translations": {"eng": "Money Heist"}},
    {"tvdb_id": "series-1", "name": "Bad id"},
    "junk",
]

SERIES = {
    "id": 81189, "name": "Breaking Bad", "year": "2008", "firstAired": "2008-01-20", "lastAired": "2013-09-29",
    "status": {"id": 2, "name": "Ended"}, "averageRuntime": 47, "overview": "A teacher...",
    "image": "https://artworks.thetvdb.com/banners/posters/81189-10.jpg",
    "genres": [{"id": 1, "name": "Drama"}, {"id": 2, "name": "Crime"}],
    "originalNetwork": {"id": 18, "name": "AMC"}, "latestNetwork": {"id": 18, "name": "AMC"},
    "contentRatings": [
        {"id": 1, "name": "TV-MA", "country": "usa", "contentType": "", "order": 1},
        {"id": 2, "name": "18", "country": "gbr", "order": 2},
        {"id": 3, "name": "16", "country": "DE", "order": 3},
        {"id": 4, "name": "X", "country": "zzz", "order": 4},
    ],
    "remoteIds": [
        {"id": "tt0903747", "type": 2, "sourceName": "IMDB"},
        {"id": "1396", "type": 12, "sourceName": "TheMovieDB.com"},
        {"id": "garbage", "type": 2, "sourceName": "IMDB"},
    ],
    "translations": {
        "nameTranslations": [{"language": "eng", "name": "Breaking Bad"}],
        "overviewTranslations": [{"language": "eng", "overview": "Walter White, a chemistry teacher..."}],
    },
}

MOVIE = {
    "id": 169, "name": "The Matrix", "year": "1999", "runtime": 136,
    "first_release": {"country": "usa", "date": "1999-03-31"},
    "companies": {"studio": [{"name": "Warner Bros."}], "production": [{"name": "Village Roadshow"}], "network": []},
    "contentRatings": [{"name": "R", "country": "usa"}],
    "remoteIds": [{"id": "tt0133093", "sourceName": "IMDB"}],
}


class Sequence:
    """Successive responses for one endpoint (a JSON list is just data)."""

    def __init__(self, values):
        self.values = list(values)

    def next(self):
        return self.values.pop(0)


class _TvdbCase(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.provider = TheTVDBProvider(configuration={}, secrets={"api_key": KEY})
        self.responses = {}
        self.calls = []

        def fake(url, **kwargs):
            self.calls.append((url, kwargs))
            path = urlparse(url).path.replace("/v4", "", 1)
            if path == "/login":
                return {"status": "success", "data": {"token": "jwt-token"}}
            value = self.responses.get(path)
            if isinstance(value, Sequence):
                value = value.next()
            if isinstance(value, Exception):
                raise value
            if value is None:
                raise ProviderHttpError("x", status=404)
            return {"status": "success", "data": value}

        patcher = patch("integrations.providers.tvdb.request_json", side_effect=fake)
        sleep = patch("integrations.providers.tvdb.time.sleep")
        patcher.start()
        sleep.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(sleep.stop)

    def api_calls(self):
        return [(url, kwargs) for url, kwargs in self.calls if not url.endswith("/login")]

    def logins(self):
        return [kwargs for url, kwargs in self.calls if url.endswith("/login")]


class DefinitionTests(SimpleTestCase):
    def test_catalog_entry(self):
        row = {item["key"]: item for item in provider_catalog()}["tvdb"]
        self.assertEqual(row["metadata_id_namespace"], "tvdb")
        self.assertEqual(row["attribution"], TVDB_ATTRIBUTION)
        fields = {field["name"]: field for field in row["fields"]}
        self.assertTrue(fields["api_key"]["required"])
        self.assertFalse(fields["pin"]["required"])

    def test_validation(self):
        with self.assertRaises(ValueError):
            TheTVDBProvider(configuration={}, secrets={"api_key": "bad key"}).validate()
        with self.assertRaises(ValueError):
            TheTVDBProvider(configuration={}, secrets={"api_key": KEY, "pin": "1 2"}).validate()


class AuthTests(_TvdbCase):
    def test_login_once_and_bearer_token(self):
        self.responses["/search"] = SEARCH
        self.provider.search_metadata(target_type="series", query="Breaking Bad")
        self.provider.search_metadata(target_type="series", query="Dark")
        self.assertEqual(len(self.logins()), 1)
        login = self.logins()[0]
        self.assertEqual((login["method"], login["json_body"]), ("POST", {"apikey": KEY}))
        url, kwargs = self.api_calls()[0]
        self.assertEqual(kwargs["headers"], {"Authorization": "Bearer jwt-token"})
        self.assertNotIn(KEY, url)

    def test_pin_is_sent_when_set(self):
        provider = TheTVDBProvider(configuration={}, secrets={"api_key": KEY, "pin": "ABCD1234"})
        self.responses["/search"] = SEARCH
        provider.search_metadata(target_type="series", query="x")
        self.assertEqual(self.logins()[0]["json_body"], {"apikey": KEY, "pin": "ABCD1234"})

    def test_expired_token_is_renewed_once(self):
        # The first lookup is refused (expired token); after a fresh login it succeeds.
        self.responses["/series/81189/extended"] = Sequence([ProviderHttpError("x", status=401), SERIES])
        detail = self.provider.get_metadata(target_type="series", source_id="81189")
        self.assertEqual(detail.title, "Breaking Bad")
        self.assertEqual(len(self.logins()), 2)

    def test_repeated_401_is_reported_not_looped(self):
        self.responses["/series/81189/extended"] = Sequence([ProviderHttpError("x", status=401)] * 3)
        with self.assertRaises(MetadataProviderError) as ctx:
            self.provider.get_metadata(target_type="series", source_id="81189")
        self.assertEqual(ctx.exception.category, MetadataErrorCategory.INVALID_CREDENTIALS)
        self.assertEqual(len(self.logins()), 2)

    def test_bad_key_at_login(self):
        def reject(url, **kwargs):
            raise ProviderHttpError("x", status=401)

        with (
            patch("integrations.providers.tvdb.request_json", side_effect=reject),
            self.assertRaises(MetadataProviderError) as ctx,
        ):
            self.provider.test_connection()
        self.assertEqual(ctx.exception.category, MetadataErrorCategory.INVALID_CREDENTIALS)
        self.assertNotIn(KEY, ctx.exception.message)


class SearchTests(_TvdbCase):
    def test_search_normalization_and_paging(self):
        self.responses["/search"] = SEARCH
        results = self.provider.search_metadata(target_type="series", query="Breaking Bad", year=2008, page=2)
        params = {key: value[0] for key, value in parse_qs(urlparse(self.api_calls()[0][0]).query).items()}
        self.assertEqual(params["type"], "series")
        self.assertEqual(params["year"], "2008")
        self.assertEqual(params["offset"], "20")
        self.assertEqual([item.source_id for item in results], ["81189", "362696"])
        self.assertEqual(results[0].release_date, PartialDate(2008, 1, 20))
        self.assertEqual({item.namespace for item in results[0].external_ids}, {"tvdb", "imdb"})
        self.assertEqual((results[1].title, results[1].original_title), ("Money Heist", "La casa de papel"))

    def test_no_results_is_empty(self):
        self.responses["/search"] = ProviderHttpError("x", status=404)
        self.assertEqual(self.provider.search_metadata(target_type="movie", query="zzz"), [])


class DetailTests(_TvdbCase):
    def test_series_details(self):
        self.responses["/series/81189/extended"] = SERIES
        detail = self.provider.get_metadata(target_type="series", source_id="81189")
        params = parse_qs(urlparse(self.api_calls()[0][0]).query)
        self.assertEqual((params["meta"], params["short"]), (["translations"], ["true"]))
        self.assertEqual(detail.overview, "Walter White, a chemistry teacher...")
        self.assertEqual(detail.end_date, PartialDate(2013, 9, 29))
        self.assertEqual(detail.networks, ("AMC",))
        self.assertEqual(detail.runtime_minutes, 47)
        self.assertEqual(
            {item.territory: item.value for item in detail.content_ratings}, {"US": "TV-MA", "GB": "18", "DE": "16"}
        )
        self.assertEqual(
            {item.namespace: item.value for item in detail.external_ids},
            {"tvdb": "81189", "imdb": "tt0903747", "tmdb": "1396"},
        )
        self.assertEqual(len(detail.artwork), 1)

    def test_continuing_series_has_no_end_date(self):
        self.responses["/series/81189/extended"] = {**SERIES, "status": {"name": "Continuing"}}
        self.assertIsNone(self.provider.get_metadata(target_type="series", source_id="81189").end_date)

    def test_movie_details(self):
        self.responses["/movies/169/extended"] = MOVIE
        detail = self.provider.get_metadata(target_type="movie", source_id="169")
        self.assertEqual(detail.release_date, PartialDate(1999, 3, 31))
        self.assertEqual(detail.studios, ("Warner Bros.", "Village Roadshow"))
        self.assertEqual(detail.content_ratings[0].to_dict(), {"value": "R", "territory": "US"})
        self.assertEqual(detail.runtime_minutes, 136)

    def test_validation_and_errors(self):
        with self.assertRaises(MetadataProviderError) as ctx:
            self.provider.get_metadata(target_type="series", source_id="tt0903747")
        self.assertEqual(ctx.exception.category, MetadataErrorCategory.INVALID_REQUEST)
        self.responses["/series/81189/extended"] = {**SERIES, "id": 1}
        with self.assertRaises(MetadataProviderError) as ctx:
            self.provider.get_metadata(target_type="series", source_id="81189")
        self.assertEqual(ctx.exception.category, MetadataErrorCategory.MALFORMED_RESPONSE)
        with self.assertRaises(MetadataProviderError) as ctx:
            self.provider.get_metadata(target_type="series", source_id="999")
        self.assertEqual(ctx.exception.category, MetadataErrorCategory.NOT_FOUND)
