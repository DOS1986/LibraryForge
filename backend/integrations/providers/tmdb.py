"""TMDB (The Movie Database) movie and series metadata adapter.

Only this module understands TMDB JSON keys and endpoint conventions. It
translates TMDB responses into LibraryForge's normalized metadata types and
never writes catalog data.

Verified against TMDB's developer documentation and API terms (2026-11-14):

* v3 base URL ``https://api.themoviedb.org/3``; the "API Read Access Token"
  is sent as ``Authorization: Bearer`` (TMDB's default method), which keeps
  the credential out of request URLs.
* HTTP 401 = invalid/suspended credentials, 404 = not found, 429 = rate
  limited (upper limit "in the 40 requests per second range"). Search pages
  run from 1 to 500.
* Image URLs are ``https://image.tmdb.org/t/p/<size><file_path>``.
* The API terms forbid caching TMDB content for longer than 6 months, require
  attribution, and do not permit commercial use without a TMDB agreement.
  LibraryForge only keeps short-lived cache entries (minutes), and each
  installation brings its own credential.
"""

from __future__ import annotations

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

TMDB_API_ROOT = "https://api.themoviedb.org/3"
TMDB_IMAGE_ROOT = "https://image.tmdb.org/t/p"
TMDB_CANDIDATE_IMAGE_SIZE = "w342"
TMDB_ARTWORK_IMAGE_SIZE = "original"
TMDB_MAX_SEARCH_PAGE = 500

TMDB_ATTRIBUTION = (
    "This product uses TMDB and the TMDB APIs but is not endorsed, certified, "
    "or otherwise approved by TMDB."
)

SEARCH_CACHE_SECONDS = 15 * 60
DETAIL_CACHE_SECONDS = 60 * 60
REQUEST_TIMEOUT_SECONDS = 8.0
MAX_ATTEMPTS = 2
MAX_INLINE_RETRY_WAIT_SECONDS = 2.0

# TMDB release_dates "type" values: 1 Premiere, 2 Theatrical (limited),
# 3 Theatrical, 4 Digital, 5 Physical, 6 TV. Prefer the general theatrical
# certification, then other public releases.
_RELEASE_TYPE_PREFERENCE = (3, 2, 4, 5, 6, 1)

_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9._~+/=-]{20,2048}$")
_TMDB_ID_PATTERN = re.compile(r"^[1-9][0-9]{0,9}$")
_IMAGE_PATH_PATTERN = re.compile(r"^/[A-Za-z0-9_-]{1,128}\.(?:jpg|jpeg|png|svg|webp)$")
_IMDB_ID_PATTERN = re.compile(r"^tt[0-9]{5,12}$")
_WIKIDATA_ID_PATTERN = re.compile(r"^Q[1-9][0-9]{0,11}$")
_NOT_FOUND_STATUS_CODES = {6, 21, 34}
_SERIES_ENDED_STATUSES = {"ended", "canceled", "cancelled"}


def _text(value: Any, max_length: int) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    return text if len(text) <= max_length else ""


def _partial_date(value: Any) -> PartialDate | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return PartialDate.parse(value.strip()[:10])
    except ValueError:
        return None


def _positive_int(value: Any, maximum: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 < value <= maximum else None


def _names(values: Any, *, limit: int = 100) -> list[str]:
    if not isinstance(values, list):
        return []
    output: list[str] = []
    for item in values[:limit]:
        name = _text(item.get("name") if isinstance(item, dict) else None, 128)
        if name:
            output.append(name)
    return output


def _image_url(path: Any, size: str) -> str:
    if not isinstance(path, str) or not _IMAGE_PATH_PATTERN.fullmatch(path):
        return ""
    return f"{TMDB_IMAGE_ROOT}/{size}{path}"


def _territory(value: Any) -> str:
    if isinstance(value, str) and re.fullmatch(r"[A-Z]{2}", value.strip().upper()):
        return value.strip().upper()
    return ""


class TMDbProvider(IntegrationProvider):
    definition = ProviderDefinition(
        key="tmdb",
        label="TMDB",
        description=(
            "Search The Movie Database for movies and TV series and review their details. "
            "LibraryForge never changes your catalog without your approval. "
            + TMDB_ATTRIBUTION
        ),
        capabilities=(CAPABILITY_METADATA,),
        fields=(
            FieldDefinition(
                name="access_token",
                label="API Read Access Token",
                secret=True,
                placeholder="TMDB API Read Access Token",
                help_text=(
                    "Found under Settings > API on themoviedb.org. "
                    "Used only by the LibraryForge backend as a Bearer token."
                ),
            ),
        ),
        online_video=False,
        storage_policy="transient",
        credential_mode=CREDENTIAL_USER,
        credential_summary=(
            "Bring your own TMDB API Read Access Token. TMDB's API terms apply to its use, "
            "including attribution and their non-commercial license."
        ),
        metadata_target_types=(MetadataTargetType.MOVIE.value, MetadataTargetType.SERIES.value),
        attribution=TMDB_ATTRIBUTION,
        metadata_id_namespace="tmdb",
    )

    # ------------------------------------------------------------------
    # Configuration and transport
    # ------------------------------------------------------------------

    @property
    def access_token(self) -> str:
        return str(self.secrets.get("access_token", "")).strip()

    def validate(self) -> None:
        super().validate()
        if not _TOKEN_PATTERN.fullmatch(self.access_token):
            raise ValueError("TMDB API Read Access Token is not in the expected format.")

    def _cache_key(self, *parts: Any) -> str:
        scope = hashlib.sha256(self.access_token.encode("utf-8")).hexdigest()[:16]
        digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:32]
        return f"libraryforge:tmdb:{scope}:{digest}"

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            self.validate()
        except ValueError as exc:
            raise MetadataProviderError(MetadataErrorCategory.INVALID_CONFIGURATION, str(exc)) from exc

        query = urlencode({key: value for key, value in (params or {}).items() if value not in (None, "")})
        url = f"{TMDB_API_ROOT}{path}" + (f"?{query}" if query else "")
        headers = {"Authorization": f"Bearer {self.access_token}"}

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                payload = request_json(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
            except ProviderHttpError as exc:
                error = self._map_http_error(exc)
                wait = self._retry_wait(error, attempt)
                if wait is None:
                    raise error from exc
                time.sleep(wait)
                continue
            return self._checked_payload(payload)

        raise AssertionError("unreachable")  # pragma: no cover

    @staticmethod
    def _retry_wait(error: MetadataProviderError, attempt: int) -> float | None:
        """Seconds to wait before one bounded inline retry, or None to give up."""

        if attempt >= MAX_ATTEMPTS or not error.retryable:
            return None
        if error.retry_after_seconds is not None:
            if error.retry_after_seconds > MAX_INLINE_RETRY_WAIT_SECONDS:
                return None
            return float(error.retry_after_seconds)
        return 0.5 + random.uniform(0, 0.5)

    def _map_http_error(self, exc: ProviderHttpError) -> MetadataProviderError:
        status = exc.status
        if status in (401, 403):
            return MetadataProviderError(
                MetadataErrorCategory.INVALID_CREDENTIALS,
                "TMDB rejected the API Read Access Token.",
            )
        if status == 404:
            return MetadataProviderError(MetadataErrorCategory.NOT_FOUND, "TMDB has no matching record.")
        if status == 429:
            return MetadataProviderError(
                MetadataErrorCategory.RATE_LIMITED,
                "TMDB is rate limiting requests. Try again shortly.",
                retry_after_seconds=exc.retry_after,
            )
        if status is not None and status >= 500:
            return MetadataProviderError(MetadataErrorCategory.UNAVAILABLE, "TMDB is temporarily unavailable.")
        if status is not None:
            return MetadataProviderError(
                MetadataErrorCategory.INVALID_REQUEST,
                f"TMDB could not process the request (HTTP {status}).",
            )
        if exc.reason == "timeout":
            return MetadataProviderError(MetadataErrorCategory.TIMEOUT, "TMDB did not respond in time.")
        if exc.reason in {"invalid_json", "too_large"}:
            return MetadataProviderError(
                MetadataErrorCategory.MALFORMED_RESPONSE, "TMDB returned an unreadable response."
            )
        return MetadataProviderError(MetadataErrorCategory.UNAVAILABLE, "Unable to reach TMDB.")

    @staticmethod
    def _checked_payload(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise MetadataProviderError(
                MetadataErrorCategory.MALFORMED_RESPONSE, "TMDB returned an unexpected response."
            )
        # Some TMDB errors (e.g. code 21) arrive with HTTP 200.
        if payload.get("success") is False:
            code = payload.get("status_code")
            if code in _NOT_FOUND_STATUS_CODES:
                raise MetadataProviderError(MetadataErrorCategory.NOT_FOUND, "TMDB has no matching record.")
            raise MetadataProviderError(
                MetadataErrorCategory.MALFORMED_RESPONSE, "TMDB reported an error for this request."
            )
        return payload

    def _cached_get(self, path: str, params: dict[str, Any], timeout: int) -> dict[str, Any]:
        key = self._cache_key(path, sorted(params.items()))
        cached = cache.get(key)
        if isinstance(cached, dict):
            return cached
        payload = self._get(path, params)
        cache.set(key, payload, timeout=timeout)
        return payload

    def test_connection(self) -> dict[str, Any]:
        # The configuration endpoint is small and validates the token without
        # depending on any particular movie or series existing.
        payload = self._get("/configuration")
        images = payload.get("images") if isinstance(payload.get("images"), dict) else {}
        return {
            "ok": True,
            "message": "TMDB connection succeeded.",
            "details": {
                "poster_sizes": len(images.get("poster_sizes") or []),
                "attribution": TMDB_ATTRIBUTION,
            },
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
        if page > TMDB_MAX_SEARCH_PAGE:
            return []
        if target_type == MetadataTargetType.MOVIE:
            path = "/search/movie"
            params: dict[str, Any] = {"query": query, "year": year}
        else:
            path = "/search/tv"
            params = {"query": query, "first_air_date_year": year}
        params.update({"include_adult": "false", "language": language, "page": page})

        payload = self._cached_get(path, params, SEARCH_CACHE_SECONDS)
        results = payload.get("results")
        if not isinstance(results, list):
            raise MetadataProviderError(
                MetadataErrorCategory.MALFORMED_RESPONSE, "TMDB returned unexpected search results."
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
        """Normalize one search result; malformed individual results are skipped."""

        if not isinstance(item, dict):
            return None
        tmdb_id = _positive_int(item.get("id"), 9_999_999_999)
        if tmdb_id is None:
            return None
        if target_type == MetadataTargetType.MOVIE:
            title_key, original_key, date_key = "title", "original_title", "release_date"
        else:
            title_key, original_key, date_key = "name", "original_name", "first_air_date"
        title = _text(item.get(title_key), 512)
        if not title:
            return None
        original_title = _text(item.get(original_key), 512)
        try:
            return MetadataCandidate(
                provider=self.definition.key,
                target_type=target_type,
                source_id=str(tmdb_id),
                title=title,
                original_title="" if original_title == title else original_title,
                release_date=_partial_date(item.get(date_key)),
                overview=_text(item.get("overview"), 20_000),
                artwork_url=_image_url(item.get("poster_path"), TMDB_CANDIDATE_IMAGE_SIZE),
                external_ids=(ExternalId("tmdb", str(tmdb_id)),),
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
        if not _TMDB_ID_PATTERN.fullmatch(source_id):
            raise MetadataProviderError(MetadataErrorCategory.INVALID_REQUEST, "TMDB IDs are positive integers.")

        if target_type == MetadataTargetType.MOVIE:
            path = f"/movie/{source_id}"
            appended = "external_ids,release_dates,images"
        else:
            path = f"/tv/{source_id}"
            appended = "external_ids,content_ratings,images"
        image_language = (language or "en").split("-")[0]
        params = {
            "append_to_response": appended,
            "language": language,
            "include_image_language": f"{image_language},null",
        }
        payload = self._cached_get(path, params, DETAIL_CACHE_SECONDS)

        if str(payload.get("id")) != source_id:
            raise MetadataProviderError(
                MetadataErrorCategory.MALFORMED_RESPONSE, "TMDB returned details for a different record."
            )
        try:
            return self._metadata(target_type, source_id, payload)
        except ValueError as exc:
            raise MetadataProviderError(
                MetadataErrorCategory.MALFORMED_RESPONSE, "TMDB returned details LibraryForge could not read."
            ) from exc

    def _metadata(self, target_type: MetadataTargetType, source_id: str, payload: dict[str, Any]) -> ProviderMetadata:
        is_movie = target_type == MetadataTargetType.MOVIE
        title = _text(payload.get("title" if is_movie else "name"), 512)
        original_title = _text(payload.get("original_title" if is_movie else "original_name"), 512)

        release_date = _partial_date(payload.get("release_date" if is_movie else "first_air_date"))
        end_date = None
        runtime: int | None
        if is_movie:
            runtime = _positive_int(payload.get("runtime"), 100_000)
            ratings = self._movie_ratings(payload.get("release_dates"))
            networks: list[str] = []
        else:
            # Series runtime is a typical *episode* runtime, documented on
            # ProviderMetadata.runtime_minutes.
            episode_runtimes = payload.get("episode_run_time")
            runtime = (
                _positive_int(episode_runtimes[0], 100_000)
                if isinstance(episode_runtimes, list) and episode_runtimes
                else None
            )
            ratings = self._series_ratings(payload.get("content_ratings"))
            networks = _names(payload.get("networks"))
            # last_air_date is only an end date once the series has finished.
            if str(payload.get("status") or "").strip().casefold() in _SERIES_ENDED_STATUSES:
                end_date = _partial_date(payload.get("last_air_date"))
                if end_date and release_date and end_date.definitely_before(release_date):
                    end_date = None

        return ProviderMetadata(
            provider=self.definition.key,
            target_type=target_type,
            source_id=source_id,
            title=title,
            original_title="" if original_title == title else original_title,
            overview=_text(payload.get("overview"), 20_000),
            tagline=_text(payload.get("tagline"), 1_000),
            release_date=release_date,
            end_date=end_date,
            runtime_minutes=runtime,
            content_ratings=tuple(ratings),
            genres=tuple(_names(payload.get("genres"))),
            studios=tuple(_names(payload.get("production_companies"))),
            networks=tuple(networks),
            external_ids=tuple(self._external_ids(source_id, payload)),
            artwork=tuple(self._artwork(payload)),
            raw=payload,
        )

    @staticmethod
    def _movie_ratings(value: Any) -> list[ContentRating]:
        results = value.get("results") if isinstance(value, dict) else None
        if not isinstance(results, list):
            return []
        output: dict[str, ContentRating] = {}
        for country in results:
            if not isinstance(country, dict):
                continue
            territory = _territory(country.get("iso_3166_1"))
            releases = country.get("release_dates")
            if not territory or territory in output or not isinstance(releases, list):
                continue
            by_type: dict[int, str] = {}
            for release in releases:
                if not isinstance(release, dict):
                    continue
                certification = _text(release.get("certification"), 32)
                release_type = release.get("type")
                if certification and isinstance(release_type, int) and release_type not in by_type:
                    by_type[release_type] = certification
            for release_type in _RELEASE_TYPE_PREFERENCE:
                if release_type in by_type:
                    output[territory] = ContentRating(by_type[release_type], territory)
                    break
        return list(output.values())

    @staticmethod
    def _series_ratings(value: Any) -> list[ContentRating]:
        results = value.get("results") if isinstance(value, dict) else None
        if not isinstance(results, list):
            return []
        output: dict[str, ContentRating] = {}
        for item in results:
            if not isinstance(item, dict):
                continue
            territory = _territory(item.get("iso_3166_1"))
            rating = _text(item.get("rating"), 32)
            if territory and rating and territory not in output:
                output[territory] = ContentRating(rating, territory)
        return list(output.values())

    @staticmethod
    def _external_ids(source_id: str, payload: dict[str, Any]) -> list[ExternalId]:
        output = [ExternalId("tmdb", source_id)]
        ids = payload.get("external_ids") if isinstance(payload.get("external_ids"), dict) else {}
        imdb = _text(ids.get("imdb_id") or payload.get("imdb_id"), 32)
        if _IMDB_ID_PATTERN.fullmatch(imdb):
            output.append(ExternalId("imdb", imdb))
        tvdb = _positive_int(ids.get("tvdb_id"), 9_999_999_999)
        if tvdb is not None:
            output.append(ExternalId("tvdb", str(tvdb)))
        wikidata = _text(ids.get("wikidata_id"), 32)
        if _WIKIDATA_ID_PATTERN.fullmatch(wikidata):
            output.append(ExternalId("wikidata", wikidata))
        return output

    @staticmethod
    def _artwork(payload: dict[str, Any]) -> list[ProviderArtwork]:
        images = payload.get("images") if isinstance(payload.get("images"), dict) else {}
        output: list[ProviderArtwork] = []
        for group, kind in (("posters", ArtworkKind.POSTER), ("backdrops", ArtworkKind.BACKDROP), ("logos", ArtworkKind.LOGO)):
            items = images.get(group)
            if not isinstance(items, list):
                continue
            for item in items[:50]:
                if not isinstance(item, dict):
                    continue
                url = _image_url(item.get("file_path"), TMDB_ARTWORK_IMAGE_SIZE)
                if not url:
                    continue
                # Documented TMDB sizes: w342 for posters, w300 for backdrops and logos.
                thumbnail = _image_url(item.get("file_path"), "w342" if kind == ArtworkKind.POSTER else "w300")
                language = item.get("iso_639_1")
                try:
                    output.append(
                        ProviderArtwork(
                            url=url,
                            kind=kind,
                            width=_positive_int(item.get("width"), 100_000),
                            height=_positive_int(item.get("height"), 100_000),
                            language=language if isinstance(language, str) and language else None,
                            thumbnail_url=thumbnail,
                        )
                    )
                except ValueError:
                    continue
        if not output:
            # Fall back to the primary poster/backdrop when no image list was returned.
            for path_key, kind in (("poster_path", ArtworkKind.POSTER), ("backdrop_path", ArtworkKind.BACKDROP)):
                url = _image_url(payload.get(path_key), TMDB_ARTWORK_IMAGE_SIZE)
                if url:
                    thumbnail = _image_url(payload.get(path_key), "w342" if kind == ArtworkKind.POSTER else "w300")
                    output.append(ProviderArtwork(url=url, kind=kind, thumbnail_url=thumbnail))
        return output
