"""TheTVDB (v4 API) movie and series metadata adapter.

TheTVDB is strongest for TV: series, alternate titles, and country content
ratings, including older and regional shows. Only this module understands
TheTVDB's JSON.

Verified against TheTVDB's v4 OpenAPI spec and API information pages
(2026-11-15):

* Base ``https://api4.thetvdb.com/v4``. ``POST /login`` with ``apikey`` (and
  ``pin`` for user-supported keys) returns ``data.token``, valid for one
  month, sent as ``Authorization: Bearer``.
* ``GET /search`` (``query``, ``type`` movie|series, ``year``, ``offset``,
  ``limit``); ``GET /series/{id}/extended`` and ``GET /movies/{id}/extended``
  (``meta=translations``, ``short=true``).
* Records carry ``contentRatings`` (name, country, contentType),
  ``remoteIds`` (id, sourceName), genres, companies, and translations keyed
  by three-letter language codes ("eng"). The spec doesn't fix the rating
  country format; examples use three-letter codes, so both forms are read.
* Attribution with a direct link to TheTVDB.com must be shown to users.
  Personal and small projects are free; user-supported keys need a
  subscriber PIN. No caching limits are stated; LibraryForge keeps only
  short-lived caches.
"""

from __future__ import annotations

import hashlib
import random
import re
import time
from typing import Any
from urllib.parse import quote, urlencode

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

TVDB_API_ROOT = "https://api4.thetvdb.com/v4"
TVDB_ATTRIBUTION = "Metadata provided by TheTVDB (thetvdb.com). Please consider adding missing information or subscribing."

TOKEN_CACHE_SECONDS = 25 * 24 * 60 * 60  # tokens last a month; renew early
SEARCH_CACHE_SECONDS = 15 * 60
DETAIL_CACHE_SECONDS = 60 * 60
REQUEST_TIMEOUT_SECONDS = 10.0
SEARCH_PAGE_SIZE = 20
MAX_SEARCH_OFFSET = 5000  # TheTVDB caps search at 5k results

_KEY = re.compile(r"^[A-Za-z0-9-]{8,128}$")
_PIN = re.compile(r"^[A-Za-z0-9]{1,64}$")
_TVDB_ID = re.compile(r"^[1-9][0-9]{0,9}$")
_IMDB_ID = re.compile(r"^tt[0-9]{5,12}$")
_TYPES = {MetadataTargetType.MOVIE: "movie", MetadataTargetType.SERIES: "series"}
_ENDED = {"ended", "canceled", "cancelled"}

# ISO 3166-1 alpha-3 -> alpha-2 for countries whose ratings are commonly listed.
_COUNTRY = {
    "usa": "US", "gbr": "GB", "can": "CA", "aus": "AU", "nzl": "NZ", "irl": "IE", "deu": "DE", "aut": "AT",
    "che": "CH", "fra": "FR", "nld": "NL", "bel": "BE", "esp": "ES", "prt": "PT", "ita": "IT", "bra": "BR",
    "mex": "MX", "swe": "SE", "nor": "NO", "dnk": "DK", "fin": "FI", "jpn": "JP", "kor": "KR", "ind": "IN",
    "pol": "PL", "rus": "RU", "tur": "TR", "grc": "GR", "hun": "HU", "cze": "CZ", "arg": "AR", "chl": "CL",
    "col": "CO", "zaf": "ZA", "sgp": "SG", "phl": "PH", "mys": "MY", "tha": "TH", "twn": "TW", "hkg": "HK",
}


def _text(value: Any, max_length: int = 20_000) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    return text if len(text) <= max_length else ""


def _date(value: Any) -> PartialDate | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return PartialDate.parse(value.strip()[:10])
    except ValueError:
        return None


def _year(value: Any) -> PartialDate | None:
    match = re.match(r"^(\d{4})", str(value or ""))
    if not match:
        return None
    try:
        return PartialDate(int(match.group(1)))
    except ValueError:
        return None


def _territory(value: Any) -> str:
    code = str(value or "").strip()
    if re.fullmatch(r"[A-Za-z]{2}", code):
        return code.upper()
    return _COUNTRY.get(code.casefold(), "")


def _image(value: Any) -> str:
    url = _text(value, 2048)
    return url if url.startswith("https://") else ""


def _english(translations: Any, default: str, field: str) -> str:
    """The English translation from a record's translations, if any."""

    if isinstance(translations, dict):
        if isinstance(translations.get("eng"), str):
            return _text(translations["eng"]) or default
        entries = translations.get(field)
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and entry.get("language") == "eng":
                    value = _text(entry.get("name" if field == "nameTranslations" else "overview"))
                    if value:
                        return value
    return default


class TheTVDBProvider(IntegrationProvider):
    definition = ProviderDefinition(
        key="tvdb",
        label="TheTVDB",
        description=(
            "Look up TV series and movies in TheTVDB, which is especially strong for TV shows and their "
            "country ratings. LibraryForge never changes your catalog without your approval. "
            + TVDB_ATTRIBUTION
        ),
        capabilities=(CAPABILITY_METADATA,),
        fields=(
            FieldDefinition(
                name="api_key",
                label="API key",
                secret=True,
                placeholder="TheTVDB v4 API key",
                help_text="Create one in your TheTVDB account under API Access.",
            ),
            FieldDefinition(
                name="pin",
                label="Subscriber PIN",
                secret=True,
                required=False,
                placeholder="Only for user-supported keys",
                help_text="Leave empty unless your key is a user-supported key that needs your subscriber PIN.",
            ),
        ),
        online_video=False,
        storage_policy="transient",
        credential_mode=CREDENTIAL_USER,
        credential_summary=(
            "Bring your own TheTVDB v4 API key (and subscriber PIN for user-supported keys). TheTVDB requires "
            "attribution, which LibraryForge shows with its data."
        ),
        metadata_target_types=(MetadataTargetType.MOVIE.value, MetadataTargetType.SERIES.value),
        metadata_id_namespace="tvdb",
        attribution=TVDB_ATTRIBUTION,
    )

    @property
    def api_key(self) -> str:
        return str(self.secrets.get("api_key", "")).strip()

    @property
    def pin(self) -> str:
        return str(self.secrets.get("pin", "")).strip()

    def validate(self) -> None:
        super().validate()
        if not _KEY.fullmatch(self.api_key):
            raise ValueError("TheTVDB API key is not in the expected format.")
        if self.pin and not _PIN.fullmatch(self.pin):
            raise ValueError("TheTVDB subscriber PIN is not in the expected format.")

    def _scope(self) -> str:
        return hashlib.sha256(f"{self.api_key}:{self.pin}".encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _token(self, *, renew: bool = False) -> str:
        key = f"libraryforge:tvdb:{self._scope()}:token"
        if not renew:
            cached = cache.get(key)
            if isinstance(cached, str) and cached:
                return cached
        body = {"apikey": self.api_key}
        if self.pin:
            body["pin"] = self.pin
        try:
            payload = request_json(
                f"{TVDB_API_ROOT}/login", method="POST", json_body=body, timeout=REQUEST_TIMEOUT_SECONDS
            )
        except ProviderHttpError as exc:
            if exc.status == 401:
                raise MetadataProviderError(
                    MetadataErrorCategory.INVALID_CREDENTIALS, "TheTVDB rejected the API key or subscriber PIN."
                ) from exc
            raise self._map_error(exc) from exc
        token = (payload.get("data") or {}).get("token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise MetadataProviderError(MetadataErrorCategory.MALFORMED_RESPONSE, "TheTVDB login returned no token.")
        cache.set(key, token, timeout=TOKEN_CACHE_SECONDS)
        return token

    def _get(self, path: str, params: dict[str, Any], *, cache_seconds: int) -> Any:
        try:
            self.validate()
        except ValueError as exc:
            raise MetadataProviderError(MetadataErrorCategory.INVALID_CONFIGURATION, str(exc)) from exc

        clean = {key: value for key, value in params.items() if value not in (None, "")}
        cache_key = f"libraryforge:tvdb:{self._scope()}:" + hashlib.sha256(
            f"{path}|{sorted(clean.items())}".encode()
        ).hexdigest()[:32]
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        url = f"{TVDB_API_ROOT}{path}" + (f"?{urlencode(clean)}" if clean else "")
        renewed = False
        for attempt in range(1, 4):
            try:
                payload = request_json(
                    url, headers={"Authorization": f"Bearer {self._token()}"}, timeout=REQUEST_TIMEOUT_SECONDS
                )
                break
            except ProviderHttpError as exc:
                if exc.status == 401 and not renewed:
                    # The cached token expired or was revoked: log in again once.
                    self._token(renew=True)
                    renewed = True
                    continue
                error = self._map_error(exc)
                if attempt < 3 and error.retryable and error.category != MetadataErrorCategory.RATE_LIMITED:
                    time.sleep(0.5 + random.uniform(0, 0.5))
                    continue
                raise error from exc

        data = payload.get("data") if isinstance(payload, dict) else None
        if data is None:
            raise MetadataProviderError(MetadataErrorCategory.MALFORMED_RESPONSE, "TheTVDB returned an unexpected response.")
        cache.set(cache_key, data, timeout=cache_seconds)
        return data

    @staticmethod
    def _map_error(exc: ProviderHttpError) -> MetadataProviderError:
        status = exc.status
        if status == 401:
            return MetadataProviderError(
                MetadataErrorCategory.INVALID_CREDENTIALS, "TheTVDB rejected the API key or subscriber PIN."
            )
        if status in (400, 404):
            return MetadataProviderError(MetadataErrorCategory.NOT_FOUND, "TheTVDB has no matching record.")
        if status == 429:
            return MetadataProviderError(
                MetadataErrorCategory.RATE_LIMITED,
                "TheTVDB is limiting requests. Try again shortly.",
                retry_after_seconds=exc.retry_after,
            )
        if status is not None and status >= 500:
            return MetadataProviderError(MetadataErrorCategory.UNAVAILABLE, "TheTVDB is temporarily unavailable.")
        if status is not None:
            return MetadataProviderError(
                MetadataErrorCategory.INVALID_REQUEST, f"TheTVDB could not process the request (HTTP {status})."
            )
        if exc.reason == "timeout":
            return MetadataProviderError(MetadataErrorCategory.TIMEOUT, "TheTVDB did not respond in time.")
        if exc.reason in {"invalid_json", "too_large"}:
            return MetadataProviderError(MetadataErrorCategory.MALFORMED_RESPONSE, "TheTVDB returned an unreadable response.")
        return MetadataProviderError(MetadataErrorCategory.UNAVAILABLE, "Unable to reach TheTVDB.")

    def test_connection(self) -> dict[str, Any]:
        try:
            self.validate()
        except ValueError as exc:
            raise MetadataProviderError(MetadataErrorCategory.INVALID_CONFIGURATION, str(exc)) from exc
        self._token(renew=True)
        return {"ok": True, "message": "TheTVDB connection succeeded.", "details": {"attribution": TVDB_ATTRIBUTION}}

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
        offset = (page - 1) * SEARCH_PAGE_SIZE
        if offset >= MAX_SEARCH_OFFSET:
            return []
        try:
            results = self._get(
                "/search",
                {"query": query, "type": _TYPES[target_type], "year": year, "limit": SEARCH_PAGE_SIZE, "offset": offset},
                cache_seconds=SEARCH_CACHE_SECONDS,
            )
        except MetadataProviderError as error:
            if error.category == MetadataErrorCategory.NOT_FOUND:
                return []
            raise
        if not isinstance(results, list):
            raise MetadataProviderError(MetadataErrorCategory.MALFORMED_RESPONSE, "TheTVDB returned unexpected search results.")
        candidates = []
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
        tvdb_id = str(item.get("tvdb_id") or "").strip()
        if not _TVDB_ID.fullmatch(tvdb_id):
            return None
        original = _text(item.get("name"), 512)
        title = _english(item.get("translations"), original, "nameTranslations")
        if not title:
            return None
        ids = [ExternalId("tvdb", tvdb_id), *self._remote_ids(item.get("remote_ids"), sources="sourceName")]
        try:
            return MetadataCandidate(
                provider=self.definition.key,
                target_type=target_type,
                source_id=tvdb_id,
                title=title,
                original_title="" if original == title else original,
                release_date=_date(item.get("first_air_time")) or _year(item.get("year")),
                overview=_english(item.get("overviews"), _text(item.get("overview")), "overviewTranslations"),
                artwork_url=_image(item.get("image_url")),
                external_ids=tuple(dict.fromkeys(ids)),
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
        if not _TVDB_ID.fullmatch(source_id):
            raise MetadataProviderError(MetadataErrorCategory.INVALID_REQUEST, "TheTVDB IDs are positive integers.")
        kind = "series" if target_type == MetadataTargetType.SERIES else "movies"
        record = self._get(
            f"/{kind}/{quote(source_id)}/extended",
            {"meta": "translations", "short": "true"},
            cache_seconds=DETAIL_CACHE_SECONDS,
        )
        if not isinstance(record, dict) or str(record.get("id")) != source_id:
            raise MetadataProviderError(
                MetadataErrorCategory.MALFORMED_RESPONSE, "TheTVDB returned details for a different record."
            )
        try:
            return self._metadata(target_type, source_id, record)
        except ValueError as exc:
            raise MetadataProviderError(
                MetadataErrorCategory.MALFORMED_RESPONSE, "TheTVDB returned details LibraryForge could not read."
            ) from exc

    @staticmethod
    def _remote_ids(values: Any, *, sources: str = "sourceName") -> list[ExternalId]:
        output: dict[str, ExternalId] = {}
        for item in values if isinstance(values, list) else []:
            if not isinstance(item, dict):
                continue
            source = str(item.get(sources) or "").casefold()
            value = str(item.get("id") or "").strip()
            if "imdb" in source and _IMDB_ID.fullmatch(value):
                output.setdefault("imdb", ExternalId("imdb", value))
            elif "themoviedb" in source and re.fullmatch(r"[1-9][0-9]{0,9}", value):
                output.setdefault("tmdb", ExternalId("tmdb", value))
        return list(output.values())

    @staticmethod
    def _ratings(values: Any) -> list[ContentRating]:
        ratings: dict[str, ContentRating] = {}
        entries = [item for item in values if isinstance(item, dict)] if isinstance(values, list) else []
        for item in sorted(entries, key=lambda entry: entry.get("order") if isinstance(entry.get("order"), int) else 0):
            territory = _territory(item.get("country"))
            name = _text(item.get("name"), 32)
            if territory and name and territory not in ratings:
                try:
                    ratings[territory] = ContentRating(name, territory)
                except ValueError:
                    continue
        return list(ratings.values())

    def _metadata(self, target_type: MetadataTargetType, source_id: str, record: dict[str, Any]) -> ProviderMetadata:
        is_series = target_type == MetadataTargetType.SERIES
        translations = record.get("translations")
        original = _text(record.get("name"), 512)
        title = _english(translations, original, "nameTranslations")
        overview = _english(translations, _text(record.get("overview")), "overviewTranslations")
        genres = [_text(item.get("name"), 128) for item in record.get("genres") or [] if isinstance(item, dict)]

        networks: list[str] = []
        studios: list[str] = []
        end_date = None
        if is_series:
            release = _date(record.get("firstAired")) or _year(record.get("year"))
            for key in ("originalNetwork", "latestNetwork"):
                network = record.get(key)
                name = _text(network.get("name"), 128) if isinstance(network, dict) else ""
                if name and name not in networks:
                    networks.append(name)
            status = record.get("status")
            status_name = _text(status.get("name"), 64).casefold() if isinstance(status, dict) else ""
            if status_name in _ENDED:
                end_date = _date(record.get("lastAired"))
                if end_date and release and end_date.definitely_before(release):
                    end_date = None
            runtime = record.get("averageRuntime")
        else:
            first = record.get("first_release")
            release = (_date(first.get("date")) if isinstance(first, dict) else None) or _year(record.get("year"))
            companies = record.get("companies")
            if isinstance(companies, dict):
                for key in ("studio", "production"):
                    for company in companies.get(key) or []:
                        name = _text(company.get("name"), 128) if isinstance(company, dict) else ""
                        if name and name not in studios:
                            studios.append(name)
            runtime = record.get("runtime")

        poster = _image(record.get("image"))
        return ProviderMetadata(
            provider=self.definition.key,
            target_type=target_type,
            source_id=source_id,
            title=title,
            original_title="" if original == title else original,
            overview=overview,
            release_date=release,
            end_date=end_date,
            runtime_minutes=runtime if isinstance(runtime, int) and not isinstance(runtime, bool) and 0 < runtime <= 100_000 else None,
            content_ratings=tuple(self._ratings(record.get("contentRatings"))),
            genres=tuple(name for name in genres if name),
            studios=tuple(studios),
            networks=tuple(networks),
            external_ids=(ExternalId("tvdb", source_id), *self._remote_ids(record.get("remoteIds"))),
            artwork=(ProviderArtwork(url=poster, kind=ArtworkKind.POSTER),) if poster else (),
            raw=record,
        )
