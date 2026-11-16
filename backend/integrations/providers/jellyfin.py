"""Jellyfin media server integration (output capability).

LibraryForge doesn't read metadata from Jellyfin. It asks Jellyfin to rescan
a library after LibraryForge changes its NFO files, and it reports each
user's parental-control settings and what they can actually see.

Verified against Jellyfin's published OpenAPI spec and user docs
(2026-11-15): the API key is sent in the ``Authorization`` header;
``GET /Library/VirtualFolders`` lists libraries (Name, Locations,
CollectionType, ItemId); ``POST /Library/Refresh`` starts a scan (204);
users carry ``Policy.MaxParentalRating`` (a number) and
``Policy.BlockUnratedItems`` (Movie, Series, ...); NFO ``mpaa`` holds the
rating. Refreshing one library (``POST /Items/{id}/Refresh``), per-user item
counts (``GET /Items`` with ``userId``), and rating names
(``GET /Localization/ParentalRatings``) follow long-standing Jellyfin API
behaviour that the spec excerpt didn't confirm, so their responses are
parsed defensively.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlencode, urlparse

from integrations.providers.base import (
    CAPABILITY_OUTPUT,
    CREDENTIAL_USER,
    FieldDefinition,
    IntegrationProvider,
    ProviderDefinition,
)
from integrations.providers.http import ProviderHttpError, request_json
from metadata.providers.types import MetadataErrorCategory, MetadataProviderError

REQUEST_TIMEOUT_SECONDS = 10.0
MAX_USERS = 50
_ITEM_ID = re.compile(r"^[0-9a-fA-F-]{32,36}$")
_KEY = re.compile(r"^[A-Za-z0-9]{16,128}$")

COUNTED_TYPES = (("movies", "Movie"), ("series", "Series"))


class JellyfinProvider(IntegrationProvider):
    definition = ProviderDefinition(
        key="jellyfin",
        label="Jellyfin",
        description=(
            "Connect to your Jellyfin server so LibraryForge can rescan a library after it changes NFO files, "
            "and show each user's parental controls and what they can see."
        ),
        capabilities=(CAPABILITY_OUTPUT,),
        fields=(
            FieldDefinition(
                name="base_url",
                label="Server URL",
                placeholder="http://jellyfin.local:8096",
                help_text="The address LibraryForge's backend uses to reach Jellyfin.",
            ),
            FieldDefinition(
                name="api_key",
                label="API key",
                secret=True,
                placeholder="Jellyfin API key",
                help_text="Create one in Jellyfin under Dashboard > API Keys.",
            ),
        ),
        online_video=False,
        storage_policy="none",
        credential_mode=CREDENTIAL_USER,
        credential_summary="Use an API key from your own Jellyfin server. It remains encrypted in LibraryForge.",
    )

    # ------------------------------------------------------------------
    # Configuration and transport
    # ------------------------------------------------------------------

    @property
    def base_url(self) -> str:
        return str(self.configuration.get("base_url", "")).strip().rstrip("/")

    @property
    def api_key(self) -> str:
        return str(self.secrets.get("api_key", "")).strip()

    def validate(self) -> None:
        super().validate()
        try:
            parsed = urlparse(self.base_url)
        except ValueError as exc:
            raise ValueError("Jellyfin Server URL is invalid.") from exc
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Jellyfin Server URL must be an http(s) address without a username or password.")
        if parsed.query or parsed.fragment:
            raise ValueError("Jellyfin Server URL must not include a query or fragment.")
        if not _KEY.fullmatch(self.api_key):
            raise ValueError("Jellyfin API key is not in the expected format.")

    def _request(self, path: str, params: dict[str, Any] | None = None, *, method: str = "GET") -> Any:
        try:
            self.validate()
        except ValueError as exc:
            raise MetadataProviderError(MetadataErrorCategory.INVALID_CONFIGURATION, str(exc)) from exc
        query = urlencode({key: value for key, value in (params or {}).items() if value not in (None, "")})
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        headers = {"Authorization": f'MediaBrowser Token="{self.api_key}"'}
        try:
            return request_json(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS, method=method)
        except ProviderHttpError as exc:
            raise self._map_error(exc) from exc

    @staticmethod
    def _map_error(exc: ProviderHttpError) -> MetadataProviderError:
        status = exc.status
        if status == 401:
            return MetadataProviderError(MetadataErrorCategory.INVALID_CREDENTIALS, "Jellyfin rejected the API key.")
        if status == 403:
            return MetadataProviderError(
                MetadataErrorCategory.PERMISSION_DENIED, "The Jellyfin API key isn't allowed to do that."
            )
        if status == 404:
            return MetadataProviderError(MetadataErrorCategory.NOT_FOUND, "Jellyfin has no such item or endpoint.")
        if status is not None and status >= 500:
            return MetadataProviderError(MetadataErrorCategory.UNAVAILABLE, "Jellyfin reported a server error.")
        if status is not None:
            return MetadataProviderError(
                MetadataErrorCategory.INVALID_REQUEST, f"Jellyfin could not process the request (HTTP {status})."
            )
        if exc.reason == "timeout":
            return MetadataProviderError(MetadataErrorCategory.TIMEOUT, "Jellyfin did not respond in time.")
        if exc.reason in {"invalid_json", "too_large"}:
            return MetadataProviderError(
                MetadataErrorCategory.MALFORMED_RESPONSE, "Jellyfin returned an unreadable response."
            )
        return MetadataProviderError(MetadataErrorCategory.UNAVAILABLE, "Unable to reach the Jellyfin server.")

    @staticmethod
    def _malformed(what: str) -> MetadataProviderError:
        return MetadataProviderError(MetadataErrorCategory.MALFORMED_RESPONSE, f"Jellyfin returned unexpected {what}.")

    # ------------------------------------------------------------------
    # Server and libraries
    # ------------------------------------------------------------------

    def test_connection(self) -> dict[str, Any]:
        info = self._request("/System/Info")
        if not isinstance(info, dict):
            raise self._malformed("server information")
        return {
            "ok": True,
            "message": f"Connected to Jellyfin {info.get('Version') or ''} ({info.get('ServerName') or 'server'}).".replace(
                "  ", " "
            ),
            "details": {"server_name": info.get("ServerName"), "version": info.get("Version")},
        }

    def libraries(self) -> list[dict[str, Any]]:
        payload = self._request("/Library/VirtualFolders")
        if not isinstance(payload, list):
            raise self._malformed("library list")
        output = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("ItemId") or "")
            if not _ITEM_ID.fullmatch(item_id):
                continue
            locations = [str(value) for value in item.get("Locations") or [] if isinstance(value, str)]
            output.append(
                {
                    "id": item_id,
                    "name": str(item.get("Name") or "")[:255],
                    "collection_type": str(item.get("CollectionType") or "")[:32],
                    "locations": locations[:20],
                }
            )
        return output

    def refresh_library(self, library_id: str) -> None:
        """Scan one Jellyfin library for new and changed files, like Jellyfin's
        "Scan library": changed NFOs are re-read, existing metadata isn't replaced."""

        if not _ITEM_ID.fullmatch(library_id or ""):
            raise MetadataProviderError(MetadataErrorCategory.INVALID_REQUEST, "That isn't a Jellyfin library ID.")
        self._request(
            f"/Items/{quote(library_id)}/Refresh",
            {
                "Recursive": "true",
                "MetadataRefreshMode": "Default",
                "ImageRefreshMode": "Default",
                "ReplaceAllMetadata": "false",
                "ReplaceAllImages": "false",
            },
            method="POST",
        )

    # ------------------------------------------------------------------
    # Parental controls
    # ------------------------------------------------------------------

    def _rating_names(self) -> dict[int, list[str]]:
        try:
            payload = self._request("/Localization/ParentalRatings")
        except MetadataProviderError:
            return {}
        names: dict[int, list[str]] = {}
        for item in payload if isinstance(payload, list) else []:
            if not isinstance(item, dict):
                continue
            value = item.get("Value")
            score = item.get("RatingScore")
            if not isinstance(value, int) and isinstance(score, dict):
                value = score.get("Score")
            name = item.get("Name")
            if isinstance(value, int) and isinstance(name, str) and name:
                names.setdefault(value, []).append(name)
        return names

    def _count(self, user_id: str, item_type: str, *, unrated: bool = False) -> int | None:
        try:
            payload = self._request(
                "/Items",
                {
                    "userId": user_id,
                    "recursive": "true",
                    "includeItemTypes": item_type,
                    "hasOfficialRating": "false" if unrated else None,
                    "limit": 0,
                    "enableTotalRecordCount": "true",
                },
            )
        except MetadataProviderError:
            return None
        count = payload.get("TotalRecordCount") if isinstance(payload, dict) else None
        return count if isinstance(count, int) and count >= 0 else None

    def parental_report(self) -> dict[str, Any]:
        users = self._request("/Users")
        if not isinstance(users, list):
            raise self._malformed("user list")
        names = self._rating_names()
        rows = []
        for user in users[:MAX_USERS]:
            if not isinstance(user, dict):
                continue
            user_id = str(user.get("Id") or "")
            if not _ITEM_ID.fullmatch(user_id):
                continue
            policy = user.get("Policy") if isinstance(user.get("Policy"), dict) else {}
            max_rating = policy.get("MaxParentalRating")
            max_rating = max_rating if isinstance(max_rating, int) else None
            blocked = [str(item) for item in policy.get("BlockUnratedItems") or [] if isinstance(item, str)]
            counts = {}
            for key, item_type in COUNTED_TYPES:
                counts[key] = {
                    "visible": self._count(user_id, item_type),
                    "visible_unrated": self._count(user_id, item_type, unrated=True),
                }
            rows.append(
                {
                    "id": user_id,
                    "name": str(user.get("Name") or "")[:255],
                    "is_administrator": bool(policy.get("IsAdministrator")),
                    "is_disabled": bool(policy.get("IsDisabled")),
                    "max_parental_rating": max_rating,
                    "max_parental_rating_names": names.get(max_rating, []) if max_rating is not None else [],
                    "blocks_unrated": blocked,
                    "counts": counts,
                    "warnings": self._warnings(max_rating, blocked, counts),
                }
            )
        # Restricted (likely child) accounts first.
        rows.sort(key=lambda row: (row["max_parental_rating"] is None, row["is_administrator"], row["name"].casefold()))
        return {"users": rows}

    @staticmethod
    def _warnings(max_rating: int | None, blocked: list[str], counts: dict[str, Any]) -> list[str]:
        if max_rating is None:
            return []
        warnings = []
        for key, item_type in COUNTED_TYPES:
            unrated = counts[key]["visible_unrated"]
            if item_type not in blocked and unrated:
                label = "movies" if key == "movies" else "TV series"
                warnings.append(
                    f"{unrated} unrated {label} are visible because unrated {label} aren't blocked for this user."
                )
        return warnings
