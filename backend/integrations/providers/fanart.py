"""Fanart.tv artwork adapter for movies and TV series.

Fanart.tv is a community artwork site: posters, backgrounds, logos, banners,
and thumbs, looked up by an ID another provider supplies. It has no search,
so it only offers artwork for a title whose TMDB, IMDb, or TheTVDB ID is known.

Verified against the official Jellyfin Fanart.tv plugin's source (2026-11-15);
Fanart.tv's own API pages refused automated access, so details its docs might
add are unconfirmed and responses are parsed defensively:

* ``https://webservice.fanart.tv/v3.2/movies/<TMDB or IMDb ID>`` and
  ``https://webservice.fanart.tv/v3.2/tv/<TheTVDB ID>``.
* The project key is the ``api_key`` query parameter; an optional personal
  key is ``client_key``. Request URLs are never logged or shown.
* Movie keys such as ``movieposter``, ``moviebackground``, ``hdmovielogo``,
  ``moviebanner``, and ``moviethumb``; TV keys such as ``tvposter``,
  ``showbackground``, ``hdtvlogo``, ``tvbanner``, and ``tvthumb``. Each image
  has ``url``, ``lang`` (``00`` for no language), ``likes``, and sometimes
  ``width`` and ``height`` as strings.
* A smaller copy is at the same path with ``/fanart/`` replaced by
  ``/bigpreview/``, which is only used for showing choices.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, ClassVar

from django.core.cache import cache

from integrations.providers.base import (
    CAPABILITY_ARTWORK,
    CREDENTIAL_USER,
    FieldDefinition,
    IntegrationProvider,
    ProviderDefinition,
)
from integrations.providers.http import ProviderHttpError, request_json
from metadata.providers.types import (
    ArtworkKind,
    MetadataErrorCategory,
    MetadataProviderError,
    ProviderArtwork,
)

FANART_API_ROOT = "https://webservice.fanart.tv/v3.2"
FANART_ATTRIBUTION = "Artwork from fanart.tv, contributed by its community."

CACHE_SECONDS = 60 * 60
REQUEST_TIMEOUT_SECONDS = 8.0
MAX_PER_KIND = 30

_KEY_PATTERN = re.compile(r"^[A-Za-z0-9]{8,64}$")
_NUMERIC_ID = re.compile(r"^[0-9]{1,12}$")
_IMDB_ID = re.compile(r"^tt[0-9]{7,10}$")

_MOVIE_KEYS = (
    ("movieposter", ArtworkKind.POSTER),
    ("moviebackground", ArtworkKind.BACKDROP),
    ("hdmovielogo", ArtworkKind.LOGO),
    ("movielogo", ArtworkKind.LOGO),
    ("moviebanner", ArtworkKind.BANNER),
    ("moviethumb", ArtworkKind.THUMBNAIL),
)
_TV_KEYS = (
    ("tvposter", ArtworkKind.POSTER),
    ("showbackground", ArtworkKind.BACKDROP),
    ("hdtvlogo", ArtworkKind.LOGO),
    ("clearlogo", ArtworkKind.LOGO),
    ("tvbanner", ArtworkKind.BANNER),
    ("tvthumb", ArtworkKind.THUMBNAIL),
)


def _number(value: Any) -> int | None:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if 0 < number <= 100_000 else None


class FanartProvider(IntegrationProvider):
    definition = ProviderDefinition(
        key="fanart",
        label="Fanart.tv",
        description=(
            "Choose community posters, backgrounds, logos, banners, and thumbs for movies and TV series "
            "you've matched with TMDB, OMDb, or TheTVDB. " + FANART_ATTRIBUTION
        ),
        capabilities=(CAPABILITY_ARTWORK,),
        fields=(
            FieldDefinition(
                name="api_key",
                label="Project API key",
                secret=True,
                placeholder="Fanart.tv API key",
                help_text="Request a key from fanart.tv. Used only by the LibraryForge backend.",
            ),
            FieldDefinition(
                name="client_key",
                label="Personal API key",
                secret=True,
                required=False,
                placeholder="Optional",
                help_text="Optional. A personal key from your fanart.tv account gives faster access to new artwork.",
            ),
        ),
        storage_policy="transient",
        credential_mode=CREDENTIAL_USER,
        credential_summary="Bring your own Fanart.tv API key.",
        attribution=FANART_ATTRIBUTION,
    )

    # Which external IDs each target can be looked up by, in order of preference.
    artwork_id_namespaces: ClassVar[dict[str, tuple[str, ...]]] = {"movie": ("tmdb", "imdb"), "series": ("tvdb",)}

    @property
    def api_key(self) -> str:
        return self.secrets.get("api_key", "").strip()

    @property
    def client_key(self) -> str:
        return self.secrets.get("client_key", "").strip()

    def validate(self) -> None:
        super().validate()
        if not _KEY_PATTERN.fullmatch(self.api_key):
            raise ValueError("The Fanart.tv API key isn't in the expected format.")
        if self.client_key and not _KEY_PATTERN.fullmatch(self.client_key):
            raise ValueError("The Fanart.tv personal API key isn't in the expected format.")

    def _get(self, path: str) -> dict[str, Any] | None:
        try:
            self.validate()
        except ValueError as exc:
            raise MetadataProviderError(MetadataErrorCategory.INVALID_CONFIGURATION, str(exc)) from exc

        scope = hashlib.sha256(f"{self.api_key}:{self.client_key}".encode()).hexdigest()[:12]
        cache_key = f"libraryforge:fanart:{scope}:{path}"
        cached = cache.get(cache_key)
        if isinstance(cached, dict):
            return cached or None

        url = f"{FANART_API_ROOT}/{path}?api_key={self.api_key}"
        if self.client_key:
            url += f"&client_key={self.client_key}"
        try:
            payload = request_json(url, timeout=REQUEST_TIMEOUT_SECONDS)
        except ProviderHttpError as exc:
            if exc.status == 404:
                cache.set(cache_key, {}, timeout=CACHE_SECONDS)
                return None
            raise self._map_http_error(exc) from exc
        if payload is None:
            return None
        if not isinstance(payload, dict):
            raise MetadataProviderError(
                MetadataErrorCategory.MALFORMED_RESPONSE, "Fanart.tv returned an unexpected response."
            )
        cache.set(cache_key, payload, timeout=CACHE_SECONDS)
        return payload

    @staticmethod
    def _map_http_error(exc: ProviderHttpError) -> MetadataProviderError:
        if exc.status in (401, 403):
            return MetadataProviderError(MetadataErrorCategory.INVALID_CREDENTIALS, "Fanart.tv rejected the API key.")
        if exc.status == 429:
            return MetadataProviderError(
                MetadataErrorCategory.RATE_LIMITED,
                "Fanart.tv is rate limiting requests. Try again shortly.",
                retry_after_seconds=exc.retry_after,
            )
        if exc.reason == "timeout":
            return MetadataProviderError(MetadataErrorCategory.TIMEOUT, "Fanart.tv didn't respond in time.")
        return MetadataProviderError(MetadataErrorCategory.UNAVAILABLE, "Fanart.tv is unavailable right now.")

    def test_connection(self) -> dict[str, Any]:
        # The Matrix (TMDB 603) has artwork on every major site.
        payload = self._get("movies/603") or {}
        return {
            "ok": True,
            "message": "Fanart.tv connection succeeded.",
            "details": {"title": str(payload.get("name") or "")[:200], "attribution": FANART_ATTRIBUTION},
        }

    def find_artwork(self, *, target_type: str, external_ids: dict[str, str]) -> list[ProviderArtwork]:
        """Artwork for a movie (TMDB or IMDb ID) or series (TheTVDB ID); [] if none."""

        ids = {str(key).casefold(): str(value).strip() for key, value in (external_ids or {}).items()}
        if target_type == "movie":
            source = ids.get("tmdb") if _NUMERIC_ID.fullmatch(ids.get("tmdb", "")) else ""
            source = source or (ids.get("imdb") if _IMDB_ID.fullmatch(ids.get("imdb", "")) else "")
            path, keys = f"movies/{source}", _MOVIE_KEYS
        elif target_type == "series":
            source = ids.get("tvdb") if _NUMERIC_ID.fullmatch(ids.get("tvdb", "")) else ""
            path, keys = f"tv/{source}", _TV_KEYS
        else:
            return []
        if not source:
            return []
        payload = self._get(path)
        return self._artwork(payload or {}, keys)

    @staticmethod
    def _artwork(payload: dict[str, Any], keys) -> list[ProviderArtwork]:
        output: list[ProviderArtwork] = []
        seen: set[str] = set()
        for key, kind in keys:
            items = payload.get(key)
            if not isinstance(items, list):
                continue
            ranked = sorted(
                (item for item in items if isinstance(item, dict)),
                key=lambda item: (
                    str(item.get("lang") or "") not in ("en", "00", ""),
                    -(_number(item.get("likes")) or 0),
                ),
            )
            count = 0
            for item in ranked:
                url = str(item.get("url") or "")
                if not url.startswith("https://") or len(url) > 2048 or url in seen:
                    continue
                language = str(item.get("lang") or "")
                thumbnail = url.replace("/fanart/", "/bigpreview/", 1) if "/fanart/" in url else url
                try:
                    output.append(
                        ProviderArtwork(
                            url=url,
                            kind=kind,
                            width=_number(item.get("width")),
                            height=_number(item.get("height")),
                            language=None if language in ("", "00") else language[:8],
                            thumbnail_url=thumbnail,
                        )
                    )
                except ValueError:
                    continue
                seen.add(url)
                count += 1
                if count >= MAX_PER_KIND:
                    break
        return output
