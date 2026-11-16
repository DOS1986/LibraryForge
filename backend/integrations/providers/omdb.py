"""OMDb (Open Movie Database) movie and series metadata adapter.

OMDb serves IMDb-derived data, including the US certification ("Rated") for
most movies and many series, which makes it a useful second source when TMDB
has no US rating. Only this module understands OMDb's JSON.

Verified against OMDb's site and Terms of Use (2026-11-15):

* ``https://www.omdbapi.com/?apikey=<key>&...``. The key can only be sent as
  a query parameter, so request URLs are never logged or shown.
* ``i`` (IMDb ID), ``t`` (title), and ``s`` (search) requests, with ``type``,
  ``y``, ``plot``, and ``page`` (1-100). Free keys allow 1,000 requests a day.
* Content is licensed CC BY-NC 4.0, and the Terms of Use allow personal,
  non-commercial use only and restrict archiving. LibraryForge keeps only
  short-lived caches; the ratings a person chooses to save stay in their own
  catalog. The Poster API is patron-only, so poster URLs are references and
  are never downloaded by this adapter.

OMDb's response fields and error strings aren't documented in detail, so
responses are parsed defensively: "N/A" means missing, and errors are
classified by their wording.
"""

from __future__ import annotations

import datetime
import hashlib
import random
import re
import time
from typing import Any
from urllib.parse import urlencode

from django.core.cache import cache

from integrations.providers.base import (
    CAPABILITY_METADATA,
    CREDENTIAL_USER,
    FieldDefinition,
    IntegrationProvider,
    ProviderDefinition,
)
from integrations.providers.http import ProviderHttpError, request_json
from metadata.providers.types import (
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
)

OMDB_API_ROOT = "https://www.omdbapi.com/"
OMDB_MAX_SEARCH_PAGE = 100

OMDB_ATTRIBUTION = (
    "Data from the OMDb API (omdbapi.com), licensed CC BY-NC 4.0. "
    "OMDb is not endorsed by or affiliated with IMDb.com."
)

SEARCH_CACHE_SECONDS = 15 * 60
DETAIL_CACHE_SECONDS = 60 * 60
REQUEST_TIMEOUT_SECONDS = 8.0
MAX_ATTEMPTS = 2

_KEY_PATTERN = re.compile(r"^[A-Za-z0-9]{6,64}$")
_IMDB_ID = re.compile(r"^tt[0-9]{7,10}$")
_YEAR = re.compile(r"(\d{4})")
_RUNTIME = re.compile(r"^(\d{1,5})\s*min", re.IGNORECASE)
_OMDB_TYPES = {MetadataTargetType.MOVIE: "movie", MetadataTargetType.SERIES: "series"}


def _value(payload: dict[str, Any], key: str, max_length: int = 20_000) -> str:
    """A field's text, with OMDb's "N/A" treated as missing."""

    value = payload.get(key)
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text or text.upper() == "N/A" or len(text) > max_length:
        return ""
    return text


def _years(value: str) -> tuple[int | None, int | None]:
    """Start and end year from "1999", "2008–2013", or an ongoing "2019–"."""

    found = [int(item) for item in _YEAR.findall(value or "")]
    start = found[0] if found else None
    end = found[1] if len(found) > 1 else None
    return start, end


def _partial_year(year: int | None) -> PartialDate | None:
    if year is None:
        return None
    try:
        return PartialDate(year)
    except ValueError:
        return None


def _released(value: str) -> PartialDate | None:
    """OMDb's "31 Mar 1999" form."""

    try:
        parsed = datetime.datetime.strptime(value, "%d %b %Y").date()  # noqa: DTZ007 - a calendar date, no time zone involved
    except ValueError:
        return None
    try:
        return PartialDate(parsed.year, parsed.month, parsed.day)
    except ValueError:
        return None


def _poster(value: str) -> str:
    return value if value.startswith("https://") and len(value) <= 2048 else ""


class OMDbProvider(IntegrationProvider):
    definition = ProviderDefinition(
        key="omdb",
        label="OMDb",
        description=(
            "Look up movies and TV series in the Open Movie Database, which uses IMDb data "
            "including US ratings. LibraryForge never changes your catalog without your approval. "
            + OMDB_ATTRIBUTION
        ),
        capabilities=(CAPABILITY_METADATA,),
        fields=(
            FieldDefinition(
                name="api_key",
                label="API key",
                secret=True,
                placeholder="OMDb API key",
                help_text="Request a key at omdbapi.com. Used only by the LibraryForge backend.",
            ),
        ),
        online_video=False,
        storage_policy="transient",
        credential_mode=CREDENTIAL_USER,
        credential_summary=(
            "Bring your own OMDb API key (free keys allow 1,000 requests a day). OMDb's terms allow "
            "personal, non-commercial use."
        ),
        metadata_target_types=(MetadataTargetType.MOVIE.value, MetadataTargetType.SERIES.value),
        metadata_id_namespace="imdb",
        attribution=OMDB_ATTRIBUTION,
    )

    @property
    def api_key(self) -> str:
        return str(self.secrets.get("api_key", "")).strip()

    def validate(self) -> None:
        super().validate()
        if not _KEY_PATTERN.fullmatch(self.api_key):
            raise ValueError("OMDb API key is not in the expected format.")

    def _cache_key(self, params: dict[str, Any]) -> str:
        scope = hashlib.sha256(self.api_key.encode("utf-8")).hexdigest()[:16]
        digest = hashlib.sha256(repr(sorted(params.items())).encode("utf-8")).hexdigest()[:32]
        return f"libraryforge:omdb:{scope}:{digest}"

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _get(self, params: dict[str, Any], *, cache_seconds: int | None = None) -> dict[str, Any]:
        try:
            self.validate()
        except ValueError as exc:
            raise MetadataProviderError(MetadataErrorCategory.INVALID_CONFIGURATION, str(exc)) from exc

        clean = {key: value for key, value in params.items() if value not in (None, "")}
        key = self._cache_key(clean)
        if cache_seconds:
            cached = cache.get(key)
            if isinstance(cached, dict):
                return cached

        url = f"{OMDB_API_ROOT}?{urlencode({**clean, 'r': 'json', 'apikey': self.api_key})}"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                payload = request_json(url, timeout=REQUEST_TIMEOUT_SECONDS)
                break
            except ProviderHttpError as exc:
                error = self._map_http_error(exc)
                if attempt >= MAX_ATTEMPTS or not error.retryable or error.category == MetadataErrorCategory.RATE_LIMITED:
                    raise error from exc
                time.sleep(0.5 + random.uniform(0, 0.5))

        if not isinstance(payload, dict):
            raise MetadataProviderError(
                MetadataErrorCategory.MALFORMED_RESPONSE, "OMDb returned an unexpected response."
            )
        if str(payload.get("Response", "")).casefold() == "false":
            # Errors are only cached as "not found", which is stable; the
            # caller decides what not-found means (empty search, missing ID).
            raise self._map_error_message(str(payload.get("Error") or ""))
        if cache_seconds:
            cache.set(key, payload, timeout=cache_seconds)
        return payload

    @staticmethod
    def _map_http_error(exc: ProviderHttpError) -> MetadataProviderError:
        status = exc.status
        if status == 401:
            return MetadataProviderError(
                MetadataErrorCategory.INVALID_CREDENTIALS,
                "OMDb rejected the API key, or the key's daily request limit was reached.",
            )
        if status == 404:
            return MetadataProviderError(MetadataErrorCategory.NOT_FOUND, "OMDb has no matching record.")
        if status == 429:
            return MetadataProviderError(
                MetadataErrorCategory.RATE_LIMITED,
                "OMDb's request limit was reached. Try again later.",
                retry_after_seconds=exc.retry_after,
            )
        if status is not None and status >= 500:
            return MetadataProviderError(MetadataErrorCategory.UNAVAILABLE, "OMDb is temporarily unavailable.")
        if status is not None:
            return MetadataProviderError(
                MetadataErrorCategory.INVALID_REQUEST, f"OMDb could not process the request (HTTP {status})."
            )
        if exc.reason == "timeout":
            return MetadataProviderError(MetadataErrorCategory.TIMEOUT, "OMDb did not respond in time.")
        if exc.reason in {"invalid_json", "too_large"}:
            return MetadataProviderError(
                MetadataErrorCategory.MALFORMED_RESPONSE, "OMDb returned an unreadable response."
            )
        return MetadataProviderError(MetadataErrorCategory.UNAVAILABLE, "Unable to reach OMDb.")

    @staticmethod
    def _map_error_message(message: str) -> MetadataProviderError:
        text = message.casefold()
        if "not found" in text or "incorrect imdb id" in text:
            return MetadataProviderError(MetadataErrorCategory.NOT_FOUND, "OMDb has no matching record.")
        if "api key" in text:
            return MetadataProviderError(MetadataErrorCategory.INVALID_CREDENTIALS, "OMDb rejected the API key.")
        if "limit" in text:
            return MetadataProviderError(
                MetadataErrorCategory.RATE_LIMITED, "OMDb's daily request limit was reached. Try again tomorrow."
            )
        if "too many results" in text:
            return MetadataProviderError(
                MetadataErrorCategory.INVALID_REQUEST, "Too many OMDb results. Add more of the title or a year."
            )
        return MetadataProviderError(MetadataErrorCategory.MALFORMED_RESPONSE, "OMDb reported an error for this request.")

    def test_connection(self) -> dict[str, Any]:
        # A lookup of one well-known title validates the key cheaply.
        payload = self._get({"i": "tt0133093"})
        return {
            "ok": True,
            "message": "OMDb connection succeeded.",
            "details": {"title": _value(payload, "Title", 512), "attribution": OMDB_ATTRIBUTION},
        }

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _search_metadata(
        self,
        *,
        target_type: MetadataTargetType,
        query: str,
        year: int | None,
        language: str | None,
        page: int,
        limit: int,
    ) -> list[MetadataCandidate]:
        if page > OMDB_MAX_SEARCH_PAGE:
            return []
        try:
            payload = self._get(
                {"s": query, "type": _OMDB_TYPES[target_type], "y": year, "page": page},
                cache_seconds=SEARCH_CACHE_SECONDS,
            )
        except MetadataProviderError as error:
            if error.category == MetadataErrorCategory.NOT_FOUND:
                return []
            raise
        results = payload.get("Search")
        if not isinstance(results, list):
            raise MetadataProviderError(
                MetadataErrorCategory.MALFORMED_RESPONSE, "OMDb returned unexpected search results."
            )
        candidates: list[MetadataCandidate] = []
        for item in results:
            candidate = self._candidate(target_type, item)
            if candidate is not None:
                candidates.append(candidate)
            if len(candidates) >= limit:
                break
        return candidates

    def _candidate(self, target_type: MetadataTargetType, item: Any) -> MetadataCandidate | None:
        if not isinstance(item, dict):
            return None
        imdb_id = _value(item, "imdbID", 16)
        title = _value(item, "Title", 512)
        if not _IMDB_ID.fullmatch(imdb_id) or not title:
            return None
        start, _end = _years(_value(item, "Year", 32))
        try:
            return MetadataCandidate(
                provider=self.definition.key,
                target_type=target_type,
                source_id=imdb_id,
                title=title,
                release_date=_partial_year(start),
                artwork_url=_poster(_value(item, "Poster", 2048)),
                external_ids=(ExternalId("imdb", imdb_id),),
            )
        except ValueError:
            return None

    # ------------------------------------------------------------------
    # Details
    # ------------------------------------------------------------------

    def _get_metadata(
        self,
        *,
        target_type: MetadataTargetType,
        source_id: str,
        language: str | None,
    ) -> ProviderMetadata:
        if not _IMDB_ID.fullmatch(source_id):
            raise MetadataProviderError(
                MetadataErrorCategory.INVALID_REQUEST, "OMDb IDs are IMDb IDs such as tt0133093."
            )
        payload = self._get({"i": source_id, "plot": "full"}, cache_seconds=DETAIL_CACHE_SECONDS)

        if _value(payload, "imdbID", 16) != source_id:
            raise MetadataProviderError(
                MetadataErrorCategory.MALFORMED_RESPONSE, "OMDb returned details for a different record."
            )
        kind = _value(payload, "Type", 32).casefold()
        if kind and kind != _OMDB_TYPES[target_type]:
            raise MetadataProviderError(
                MetadataErrorCategory.NOT_FOUND,
                f"OMDb lists {source_id} as a {kind}, not a {_OMDB_TYPES[target_type]}.",
            )
        try:
            return self._metadata(target_type, source_id, payload)
        except ValueError as exc:
            raise MetadataProviderError(
                MetadataErrorCategory.MALFORMED_RESPONSE, "OMDb returned details LibraryForge could not read."
            ) from exc

    def _metadata(self, target_type: MetadataTargetType, source_id: str, payload: dict[str, Any]) -> ProviderMetadata:
        is_series = target_type == MetadataTargetType.SERIES
        start, end = _years(_value(payload, "Year", 32))
        release = _released(_value(payload, "Released", 32))
        if release is not None and start is not None and release.year != start:
            # Released can be a later regional or re-release date; when it
            # disagrees with Year, keep only the year.
            release = None
        release = release or _partial_year(start)

        runtime_match = _RUNTIME.match(_value(payload, "Runtime", 32))
        runtime = int(runtime_match.group(1)) if runtime_match else None
        rated = _value(payload, "Rated", 32)
        genres = [item.strip() for item in _value(payload, "Genre", 1000).split(",") if item.strip()]
        production = _value(payload, "Production", 256)
        poster = _poster(_value(payload, "Poster", 2048))

        return ProviderMetadata(
            provider=self.definition.key,
            target_type=target_type,
            source_id=source_id,
            title=_value(payload, "Title", 512),
            overview=_value(payload, "Plot"),
            release_date=release,
            end_date=_partial_year(end) if is_series and end and (start is None or end >= start) else None,
            runtime_minutes=runtime if runtime and runtime > 0 else None,
            # OMDb's "Rated" is the US certification from IMDb.
            content_ratings=(ContentRating(rated, "US"),) if rated else (),
            genres=tuple(genres),
            studios=(production,) if production else (),
            external_ids=(ExternalId("imdb", source_id),),
            artwork=(ProviderArtwork(url=poster, kind=ArtworkKind.POSTER),) if poster else (),
            raw=payload,
        )
