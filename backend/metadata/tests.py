"""Contract tests for the alpha.5 metadata-provider foundation.

These tests cover normalized types, the IntegrationProvider metadata methods,
registry discovery, and compatibility with existing known-ID providers. They
make no network calls and touch no database.
"""

from unittest.mock import patch

from django.test import SimpleTestCase

from integrations.providers.base import (
    CAPABILITY_ARTWORK,
    CAPABILITY_METADATA,
    IntegrationProvider,
    ProviderDefinition,
    provider_supports_metadata_target,
)
from integrations.providers.tubearchivist import TubeArchivistProvider
from integrations.providers.youtube import YouTubeProvider
from integrations.registry import (
    _validate_definition,
    metadata_provider_classes,
    provider_catalog,
)
from metadata.providers import (
    ArtworkKind,
    ContentRating,
    ExternalId,
    MetadataCandidate,
    MetadataErrorCategory,
    MetadataProviderError,
    MetadataTargetType,
    PartialDate,
    ProviderArtwork,
    ProviderMetadata,
    deduplicate_candidates,
    parse_target_type,
)


def _candidate(source_id="603", **overrides):
    values = {
        "provider": "fake-movies",
        "target_type": "movie",
        "source_id": source_id,
        "title": "The Matrix",
        "release_date": "1999-03-30",
    }
    values.update(overrides)
    return MetadataCandidate(**values)


class _FakeMetadataProvider(IntegrationProvider):
    definition = ProviderDefinition(
        key="fake-movies",
        label="Fake Movies",
        description="Test metadata provider",
        capabilities=(CAPABILITY_METADATA, CAPABILITY_ARTWORK),
        fields=(),
        metadata_target_types=("movie", "series"),
    )

    def __init__(self, *, search_results=None, detail=None):
        super().__init__(configuration={}, secrets={})
        self.search_results = search_results if search_results is not None else []
        self.detail = detail
        self.calls = []

    def test_connection(self):
        return {"ok": True}

    def _search_metadata(self, **kwargs):
        self.calls.append(("search", kwargs))
        return self.search_results

    def _get_metadata(self, **kwargs):
        self.calls.append(("detail", kwargs))
        return self.detail


class _MovieOnlyProvider(_FakeMetadataProvider):
    definition = ProviderDefinition(
        key="fake-movies",
        label="Movie Only",
        description="Test",
        capabilities=(CAPABILITY_METADATA,),
        fields=(),
        metadata_target_types=("movie",),
    )


class TargetTypeTests(SimpleTestCase):
    def test_parse_known_targets(self):
        self.assertIs(parse_target_type("movie"), MetadataTargetType.MOVIE)
        self.assertIs(parse_target_type(" Series "), MetadataTargetType.SERIES)

    def test_episode_is_not_a_series(self):
        with self.assertRaises(MetadataProviderError) as ctx:
            parse_target_type("episode")
        self.assertEqual(ctx.exception.category, MetadataErrorCategory.UNSUPPORTED_TARGET)
        self.assertFalse(ctx.exception.retryable)


class PartialDateTests(SimpleTestCase):
    def test_year_keeps_year_precision(self):
        value = PartialDate.parse("1999")
        self.assertEqual(value, PartialDate(1999))
        self.assertEqual(value.precision, "year")
        self.assertEqual(value.isoformat(), "1999")

    def test_full_and_month_dates(self):
        self.assertEqual(PartialDate.parse("1999-03-30").precision, "day")
        self.assertEqual(PartialDate.parse("1999-03").isoformat(), "1999-03")

    def test_empty_is_missing(self):
        self.assertIsNone(PartialDate.parse(""))
        self.assertIsNone(PartialDate.parse(None))

    def test_invalid_dates_rejected(self):
        for value in ("1999-02-30", "99", "1999/03/30", "1999-13", 1999):
            with self.subTest(value=value), self.assertRaises(ValueError):
                PartialDate.parse(value)
        with self.assertRaises(ValueError):
            PartialDate(1999, None, 5)

    def test_definitely_before_respects_precision(self):
        self.assertFalse(PartialDate(1999).definitely_before(PartialDate(1999, 5, 1)))
        self.assertTrue(PartialDate(1998).definitely_before(PartialDate(1999, 5, 1)))


class ExternalIdTests(SimpleTestCase):
    def test_namespace_normalized(self):
        self.assertEqual(ExternalId("IMDB", " tt0133093 ").to_dict(), {"namespace": "imdb", "value": "tt0133093"})

    def test_invalid_namespace_and_empty_value(self):
        for namespace, value in (("bad namespace", "1"), ("", "1"), ("imdb", ""), ("x" * 33, "1")):
            with self.subTest(namespace=namespace), self.assertRaises(ValueError):
                ExternalId(namespace, value)

    def test_duplicates_collapse_and_conflicts_reject(self):
        candidate = _candidate(external_ids=(ExternalId("imdb", "tt1"), ExternalId("imdb", "tt1")))
        self.assertEqual(len(candidate.external_ids), 1)
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            _candidate(external_ids=(ExternalId("imdb", "tt1"), ExternalId("imdb", "tt2")))

    def test_mapping_input(self):
        candidate = _candidate(external_ids={"imdb": "tt1", "tvdb": ""})
        self.assertEqual([item.namespace for item in candidate.external_ids], ["imdb"])


class CandidateTests(SimpleTestCase):
    def test_serializes_identity_and_year(self):
        payload = _candidate().to_dict()
        self.assertEqual(payload["provider"], "fake-movies")
        self.assertEqual(payload["target_type"], "movie")
        self.assertEqual(payload["source_id"], "603")
        self.assertEqual(payload["year"], 1999)
        self.assertEqual(payload["release_date"], "1999-03-30")

    def test_identity_is_scoped_by_provider_and_target(self):
        movie = _candidate()
        series = _candidate(target_type="series")
        self.assertNotEqual(movie.identity, series.identity)
        self.assertEqual(len(deduplicate_candidates([movie, series, _candidate()])), 2)

    def test_text_is_bounded_and_cleaned(self):
        candidate = _candidate(title="  The\x00 Matrix \n ", overview="Line one\nLine two")
        self.assertEqual(candidate.title, "The Matrix")
        self.assertEqual(candidate.overview, "Line one\nLine two")
        with self.assertRaises(ValueError):
            _candidate(title="x" * 600)
        with self.assertRaises(ValueError):
            _candidate(title="   ")

    def test_rejects_unsafe_source_ids_and_urls(self):
        for source_id in ("", "../etc", "a b", "x" * 200, True):
            with self.subTest(source_id=source_id), self.assertRaises(ValueError):
                _candidate(source_id=source_id)
        for url in ("javascript:alert(1)", "file:///etc/passwd", "https://user:pw@example.com/a.jpg", "/a.jpg"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                _candidate(artwork_url=url)

    def test_integer_source_id_accepted(self):
        self.assertEqual(_candidate(source_id=603).source_id, "603")


class ProviderMetadataTests(SimpleTestCase):
    def _detail(self, **overrides):
        values = {
            "provider": "fake-movies",
            "target_type": "movie",
            "source_id": "603",
            "title": "The Matrix",
        }
        values.update(overrides)
        return ProviderMetadata(**values)

    def test_missing_values_stay_missing(self):
        payload = self._detail().to_dict()
        self.assertEqual(payload["overview"], "")
        self.assertIsNone(payload["release_date"])
        self.assertIsNone(payload["runtime_minutes"])
        self.assertEqual(payload["genres"], [])
        self.assertEqual(payload["artwork"], [])

    def test_raw_is_internal_and_bounded(self):
        detail = self._detail(raw={"id": 603})
        self.assertEqual(detail.raw, {"id": 603})
        self.assertNotIn("raw", detail.to_dict())
        self.assertIsNone(self._detail(raw={"blob": "x" * (300 * 1024)}).raw)
        with self.assertRaises(ValueError):
            self._detail(raw=["not", "a", "mapping"])

    def test_collections_deduplicate_case_insensitively(self):
        detail = self._detail(genres=("Action", "action", " Science  Fiction "))
        self.assertEqual(detail.genres, ("Action", "Science Fiction"))
        with self.assertRaises(ValueError):
            self._detail(genres="Action")

    def test_studios_and_networks_stay_distinct(self):
        detail = self._detail(target_type="series", studios=("Warner Bros.",), networks=("HBO",))
        self.assertEqual(detail.to_dict()["studios"], ["Warner Bros."])
        self.assertEqual(detail.to_dict()["networks"], ["HBO"])

    def test_content_ratings_are_per_territory(self):
        detail = self._detail(content_ratings=(ContentRating("R", "us"), ContentRating("15", "GB")))
        self.assertEqual(detail.to_dict()["content_ratings"][0], {"value": "R", "territory": "US"})
        with self.assertRaises(ValueError):
            self._detail(content_ratings=(ContentRating("R", "US"), ContentRating("PG", "US")))
        with self.assertRaises(ValueError):
            ContentRating("R", "USA")

    def test_dates_and_runtime_validation(self):
        series = self._detail(target_type="series", release_date="2008", end_date="2013-09-29")
        self.assertEqual(series.to_dict()["release_date_precision"], "year")
        with self.assertRaisesRegex(ValueError, "only valid for series"):
            self._detail(end_date="2001")
        with self.assertRaisesRegex(ValueError, "precedes"):
            self._detail(target_type="series", release_date="2010", end_date="2009-12")
        for runtime in (0, -5, 136.0, True):
            with self.subTest(runtime=runtime), self.assertRaises(ValueError):
                self._detail(runtime_minutes=runtime)

    def test_artwork_candidates(self):
        art = ProviderArtwork("https://images.example.com/p.jpg", kind="poster", width=1000, height=1500, language="en")
        detail = self._detail(artwork=(art, art))
        self.assertEqual(len(detail.artwork), 1)
        self.assertIs(detail.artwork[0].kind, ArtworkKind.POSTER)
        unknown = ProviderArtwork("https://images.example.com/b.jpg", kind="backdrop")
        self.assertIsNone(unknown.to_dict()["width"])
        self.assertIsNone(unknown.to_dict()["language"])
        with self.assertRaises(ValueError):
            ProviderArtwork("https://images.example.com/b.jpg", kind="banner-ish")
        with self.assertRaises(ValueError):
            ProviderArtwork("https://images.example.com/b.jpg", width=0)


class ProviderContractTests(SimpleTestCase):
    def test_supports_declared_targets_only(self):
        provider = _MovieOnlyProvider()
        self.assertTrue(provider.supports_metadata_target("movie"))
        self.assertFalse(provider.supports_metadata_target("series"))
        self.assertFalse(provider.supports_metadata_target("episode"))

    def test_metadata_capability_required(self):
        definition = ProviderDefinition(
            key="art-only",
            label="Art",
            description="",
            capabilities=(CAPABILITY_ARTWORK,),
            fields=(),
            metadata_target_types=("movie",),
        )
        self.assertFalse(provider_supports_metadata_target(definition, "movie"))

    def test_unsupported_target_fails_before_adapter_call(self):
        provider = _MovieOnlyProvider()
        for call in (
            lambda: provider.search_metadata(target_type="series", query="Breaking Bad"),
            lambda: provider.get_metadata(target_type="series", source_id="1396"),
            lambda: provider.search_metadata(target_type="episode", query="Pilot"),
        ):
            with self.assertRaises(MetadataProviderError) as ctx:
                call()
            self.assertEqual(ctx.exception.category, MetadataErrorCategory.UNSUPPORTED_TARGET)
        self.assertEqual(provider.calls, [])

    def test_search_validates_request_before_adapter_call(self):
        provider = _FakeMetadataProvider()
        bad_requests = (
            {"query": "   "},
            {"query": "x" * 201},
            {"query": "Matrix", "year": 99},
            {"query": "Matrix", "year": True},
            {"query": "Matrix", "page": 0},
            {"query": "Matrix", "limit": 51},
            {"query": "Matrix", "language": "en_US; DROP"},
        )
        for kwargs in bad_requests:
            with self.subTest(kwargs=kwargs), self.assertRaises(MetadataProviderError) as ctx:
                provider.search_metadata(target_type="movie", **kwargs)
            self.assertEqual(ctx.exception.category, MetadataErrorCategory.INVALID_REQUEST)
        self.assertEqual(provider.calls, [])

    def test_search_normalizes_query_and_returns_deduplicated_limited_results(self):
        results = [_candidate("1"), _candidate("1"), _candidate("2"), _candidate("3")]
        provider = _FakeMetadataProvider(search_results=results)
        output = provider.search_metadata(target_type="MOVIE", query="  The   Matrix ", year=1999, limit=2)
        self.assertEqual([item.source_id for item in output], ["1", "2"])
        _, kwargs = provider.calls[0]
        self.assertEqual(kwargs["query"], "The Matrix")
        self.assertIs(kwargs["target_type"], MetadataTargetType.MOVIE)

    def test_empty_search_is_success(self):
        self.assertEqual(_FakeMetadataProvider().search_metadata(target_type="series", query="Nothing"), [])

    def test_search_rejects_foreign_or_cross_type_results(self):
        for bad in (
            [_candidate(provider="other")],
            [_candidate(target_type="series")],
            [{"title": "raw dict"}],
            {"results": []},
        ):
            provider = _FakeMetadataProvider(search_results=bad)
            with self.subTest(bad=bad), self.assertRaises(MetadataProviderError) as ctx:
                provider.search_metadata(target_type="movie", query="Matrix")
            self.assertEqual(ctx.exception.category, MetadataErrorCategory.MALFORMED_RESPONSE)

    def test_get_metadata_validates_identity(self):
        detail = ProviderMetadata(provider="fake-movies", target_type="movie", source_id="603", title="The Matrix")
        provider = _FakeMetadataProvider(detail=detail)
        self.assertEqual(provider.get_metadata(target_type="movie", source_id=" 603 "), detail)

        with self.assertRaises(MetadataProviderError) as ctx:
            provider.get_metadata(target_type="movie", source_id="604")
        self.assertEqual(ctx.exception.category, MetadataErrorCategory.MALFORMED_RESPONSE)

        with self.assertRaises(MetadataProviderError) as ctx:
            provider.get_metadata(target_type="movie", source_id="../603")
        self.assertEqual(ctx.exception.category, MetadataErrorCategory.INVALID_REQUEST)

    def test_error_serialization(self):
        error = MetadataProviderError("rate_limited", "Slow down.", retry_after_seconds=30)
        self.assertTrue(error.retryable)
        self.assertEqual(
            error.to_dict(),
            {"category": "rate_limited", "message": "Slow down.", "retryable": True, "retry_after_seconds": 30},
        )
        self.assertFalse(MetadataProviderError("invalid_credentials", "Bad key").retryable)


class RegistryTests(SimpleTestCase):
    def test_catalog_exposes_metadata_target_types_with_backward_compatible_default(self):
        rows = {row["key"]: row for row in provider_catalog()}
        self.assertEqual(rows["youtube"]["metadata_target_types"], [])
        self.assertEqual(rows["tubearchivist"]["metadata_target_types"], [])

    def test_no_registered_provider_claims_movie_or_series_yet(self):
        self.assertEqual(metadata_provider_classes("movie"), [])
        self.assertEqual(metadata_provider_classes("series"), [])
        self.assertEqual(metadata_provider_classes("episode"), [])

    def test_definition_validation(self):
        class BadTarget(_FakeMetadataProvider):
            definition = ProviderDefinition(
                key="bad", label="Bad", description="", capabilities=(CAPABILITY_METADATA,), fields=(),
                metadata_target_types=("episode",),
            )

        class MissingCapability(_FakeMetadataProvider):
            definition = ProviderDefinition(
                key="bad", label="Bad", description="", capabilities=(CAPABILITY_ARTWORK,), fields=(),
                metadata_target_types=("movie",),
            )

        with self.assertRaisesRegex(ValueError, "unsupported metadata target types"):
            _validate_definition(BadTarget)
        with self.assertRaisesRegex(ValueError, "without the metadata capability"):
            _validate_definition(MissingCapability)
        _validate_definition(_FakeMetadataProvider)

    def test_registry_discovers_declared_provider(self):
        with patch.dict("integrations.registry.PROVIDERS", {"fake-movies": _MovieOnlyProvider}):
            self.assertIn(_MovieOnlyProvider, metadata_provider_classes("movie"))
            self.assertNotIn(_MovieOnlyProvider, metadata_provider_classes("series"))


class ExistingProviderCompatibilityTests(SimpleTestCase):
    """YouTube and TubeArchivist keep their known-ID lookups and gain no search."""

    def test_existing_providers_do_not_support_movie_or_series(self):
        for provider_class in (YouTubeProvider, TubeArchivistProvider):
            with self.subTest(provider=provider_class.definition.key):
                self.assertEqual(provider_class.definition.metadata_target_types, ())
                provider = provider_class(configuration={"base_url": "https://ta.example.com"}, secrets={"api_key": "k", "api_token": "t"})
                self.assertFalse(provider.supports_metadata_target("movie"))
                self.assertFalse(provider.supports_metadata_target("series"))

    def test_metadata_search_on_existing_providers_makes_no_network_request(self):
        with patch("integrations.providers.youtube.request_json") as youtube_request:
            provider = YouTubeProvider(configuration={}, secrets={"api_key": "k"})
            with self.assertRaises(MetadataProviderError) as ctx:
                provider.search_metadata(target_type="movie", query="Matrix")
            self.assertEqual(ctx.exception.category, MetadataErrorCategory.UNSUPPORTED_TARGET)
            with self.assertRaises(MetadataProviderError):
                provider.get_metadata(target_type="series", source_id="1396")
        youtube_request.assert_not_called()

    def test_known_id_lookup_methods_are_unchanged(self):
        for provider_class in (YouTubeProvider, TubeArchivistProvider):
            with self.subTest(provider=provider_class.definition.key):
                self.assertIsNot(provider_class.lookup_many, IntegrationProvider.search_metadata)
                self.assertIn("lookup_many", provider_class.__dict__)
