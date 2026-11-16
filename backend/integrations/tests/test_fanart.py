"""Fanart.tv adapter and the per-provider artwork host allowlist."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from integrations.providers.fanart import FanartProvider
from integrations.providers.http import ProviderHttpError
from integrations.security import allowed_artwork_url, artwork_url_downloadable
from metadata.providers.types import (
    ArtworkKind,
    MetadataErrorCategory,
    MetadataProviderError,
)

MOVIE = {
    "name": "The Matrix",
    "movieposter": [
        {"id": "1", "url": "https://assets.fanart.tv/fanart/movies/603/movieposter/a.jpg", "lang": "en", "likes": "2"},
        {"id": "2", "url": "https://assets.fanart.tv/fanart/movies/603/movieposter/b.jpg", "lang": "en", "likes": "7"},
    ],
    "moviebackground": [{"id": "3", "url": "https://assets.fanart.tv/fanart/movies/603/moviebackground/c.jpg", "lang": "00"}],
    "moviedisc": [{"id": "4", "url": "https://assets.fanart.tv/fanart/movies/603/moviedisc/d.png"}],
    "movielogo": "not a list",
}


class FanartProviderTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.provider = FanartProvider(configuration={}, secrets={"api_key": "abcdef0123456789", "client_key": "personal99"})
        request = patch("integrations.providers.fanart.request_json", return_value=MOVIE)
        self.request = request.start()
        self.addCleanup(request.stop)

    def test_movie_artwork_by_tmdb_id(self):
        artwork = self.provider.find_artwork(target_type="movie", external_ids={"tmdb": "603", "imdb": "tt0133093"})

        url = self.request.call_args.args[0]
        self.assertTrue(url.startswith("https://webservice.fanart.tv/v3.2/movies/603?api_key=abcdef0123456789"))
        self.assertIn("&client_key=personal99", url)
        # Most-liked first; disc art isn't offered; "00" means no language.
        self.assertEqual([item.url.rsplit("/", 1)[-1] for item in artwork], ["b.jpg", "a.jpg", "c.jpg"])
        self.assertEqual(artwork[2].kind, ArtworkKind.BACKDROP)
        self.assertIsNone(artwork[2].language)

    def test_imdb_fallback_and_cache(self):
        self.provider.find_artwork(target_type="movie", external_ids={"imdb": "tt0133093"})
        self.provider.find_artwork(target_type="movie", external_ids={"imdb": "tt0133093"})
        self.assertIn("/movies/tt0133093?", self.request.call_args.args[0])
        self.assertEqual(self.request.call_count, 1)

    def test_no_usable_id_makes_no_request(self):
        self.assertEqual(self.provider.find_artwork(target_type="series", external_ids={"tmdb": "1396"}), [])
        self.assertEqual(self.provider.find_artwork(target_type="movie", external_ids={"tmdb": "../x"}), [])
        self.request.assert_not_called()

    def test_not_found_is_empty_and_bad_keys_are_explained(self):
        self.request.side_effect = ProviderHttpError("missing", 404)
        self.assertEqual(self.provider.find_artwork(target_type="series", external_ids={"tvdb": "1"}), [])

        self.request.side_effect = ProviderHttpError("denied", 401)
        with self.assertRaises(MetadataProviderError) as raised:
            self.provider.find_artwork(target_type="series", external_ids={"tvdb": "2"})
        self.assertEqual(raised.exception.category, MetadataErrorCategory.INVALID_CREDENTIALS)

    def test_malformed_key_is_rejected_before_any_request(self):
        provider = FanartProvider(configuration={}, secrets={"api_key": "bad key!"})
        with self.assertRaises(MetadataProviderError):
            provider.find_artwork(target_type="movie", external_ids={"tmdb": "603"})
        self.request.assert_not_called()


class ArtworkHostTests(SimpleTestCase):
    def test_hosts_are_limited_to_each_providers_own(self):
        self.assertTrue(artwork_url_downloadable("https://image.tmdb.org/t/p/original/a.jpg", "tmdb"))
        self.assertFalse(artwork_url_downloadable("http://image.tmdb.org/t/p/original/a.jpg", "tmdb"))
        self.assertFalse(artwork_url_downloadable("https://image.tmdb.org/t/p/original/a.jpg", "fanart"))
        self.assertFalse(artwork_url_downloadable("https://image.tmdb.org.evil.example/a.jpg", "tmdb"))
        self.assertTrue(artwork_url_downloadable("https://assets.fanart.tv/fanart/a.jpg", "fanart"))
        self.assertFalse(artwork_url_downloadable("https://m.media-amazon.com/images/a.jpg", "omdb"))

    def test_fetcher_allows_provider_hosts(self):
        self.assertTrue(
            allowed_artwork_url(artwork_url="https://artworks.thetvdb.com/banners/a.jpg", provider=None, connection_provider="tvdb")
        )
        self.assertFalse(
            allowed_artwork_url(artwork_url="https://artworks.thetvdb.com/banners/a.jpg", provider=None, connection_provider="tmdb")
        )
