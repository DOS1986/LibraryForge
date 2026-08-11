from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import urlencode

from django.core.cache import cache

from integrations.providers.base import (
    CAPABILITY_ARTWORK,
    CAPABILITY_CATALOG,
    CAPABILITY_METADATA,
    CREDENTIAL_USER,
    FieldDefinition,
    IntegrationProvider,
    ProviderDefinition,
)
from integrations.providers.http import request_json


YOUTUBE_API_ROOT = "https://www.googleapis.com/youtube/v3"


class YouTubeProvider(IntegrationProvider):
    definition = ProviderDefinition(
        key="youtube",
        label="YouTube",
        description=(
            "Read current metadata and artwork for existing YouTube channel, video, and playlist IDs. "
            "LibraryForge never downloads media or manages subscriptions."
        ),
        capabilities=(CAPABILITY_METADATA, CAPABILITY_ARTWORK, CAPABILITY_CATALOG),
        fields=(
            FieldDefinition(
                name="api_key",
                label="API key",
                secret=True,
                placeholder="YouTube Data API v3 key",
                help_text="Used only by the LibraryForge backend for read-only YouTube Data API requests.",
            ),
        ),
        online_video=True,
        storage_policy="transient",
        credential_mode=CREDENTIAL_USER,
        credential_summary=(
            "Bring your own YouTube Data API v3 key. LibraryForge never ships or shares a global YouTube API key."
        ),
    )

    @property
    def api_key(self) -> str:
        return self.secrets.get("api_key", "").strip()

    def _cache_key(self, target_type: str, source_id: str) -> str:
        key_hash = hashlib.sha256(self.api_key.encode("utf-8")).hexdigest()[:12]
        return f"libraryforge:youtube:{key_hash}:{target_type}:{source_id}"

    def _get(self, resource: str, params: dict[str, str]) -> Any:
        self.validate()
        query = urlencode({**params, "key": self.api_key})
        return request_json(f"{YOUTUBE_API_ROOT}/{resource}?{query}")

    def test_connection(self) -> dict[str, Any]:
        # videoCategories is a tiny public read that validates the API key without
        # depending on one particular video/channel remaining available.
        payload = self._get(
            "videoCategories",
            {"part": "snippet", "regionCode": "US"},
        )
        return {
            "ok": True,
            "message": "YouTube Data API connection succeeded.",
            "details": {"returned_categories": len(payload.get("items") or [])},
        }

    @staticmethod
    def _thumbnail_url(snippet: dict[str, Any]) -> str:
        thumbnails = snippet.get("thumbnails") or {}
        for key in ("maxres", "standard", "high", "medium", "default"):
            value = thumbnails.get(key) or {}
            url = value.get("url")
            if url:
                return str(url)
        return ""

    def lookup_many(self, *, target_type: str, source_ids: list[str]) -> dict[str, dict[str, Any]]:
        ids = [value for value in dict.fromkeys(source_ids) if value]
        if not ids:
            return {}

        if target_type == "channel":
            resource = "channels"
            parts = "snippet"
        elif target_type == "online_video":
            resource = "videos"
            parts = "snippet,contentDetails"
        elif target_type == "playlist":
            resource = "playlists"
            parts = "snippet"
        else:
            return {}

        output: dict[str, dict[str, Any]] = {}
        missing: list[str] = []

        for source_id in ids:
            cached = cache.get(self._cache_key(target_type, source_id))
            if isinstance(cached, dict):
                output[source_id] = cached
            else:
                missing.append(source_id)

        for offset in range(0, len(missing), 50):
            batch = missing[offset : offset + 50]
            payload = self._get(
                resource,
                {"part": parts, "id": ",".join(batch), "maxResults": "50"},
            )
            returned_ids: set[str] = set()
            for item in payload.get("items") or []:
                source_id = str(item.get("id") or "")
                if not source_id:
                    continue
                returned_ids.add(source_id)
                snippet = item.get("snippet") or {}
                normalized = {
                    "provider": "youtube",
                    "source_id": source_id,
                    "title": snippet.get("title") or "",
                    "description": snippet.get("description") or "",
                    "published_at": snippet.get("publishedAt"),
                    "channel_id": snippet.get("channelId") or "",
                    "channel_title": snippet.get("channelTitle") or "",
                    "tags": snippet.get("tags") or [],
                    "category_id": snippet.get("categoryId") or "",
                    "artwork_url": self._thumbnail_url(snippet),
                    "raw": item,
                }
                output[source_id] = normalized
                # Short-lived process/cache data only. This is deliberately not
                # written into LibraryForge's persistent metadata tables.
                cache.set(self._cache_key(target_type, source_id), normalized, timeout=900)

            # Cache a small miss marker so deleted/private IDs are not hammered
            # repeatedly during one browsing session.
            for source_id in batch:
                if source_id not in returned_ids:
                    cache.set(self._cache_key(target_type, source_id), {}, timeout=300)

        return output
