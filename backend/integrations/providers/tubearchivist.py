from __future__ import annotations

import re
from typing import Any
from urllib.parse import (
    urljoin,
    urlparse,
)

from integrations.providers.base import (
    CAPABILITY_ARTWORK,
    CAPABILITY_CATALOG,
    CAPABILITY_METADATA,
    CREDENTIAL_USER,
    FieldDefinition,
    IntegrationProvider,
    ProviderDefinition,
)
from integrations.providers.http import (
    ProviderHttpError,
    request_json,
)


_IMAGE_KEY_HINTS = (
    "thumb",
    "thumbnail",
    "cover",
    "banner",
    "artwork",
    "icon",
    "avatar",
)

_SAFE_SOURCE_ID = re.compile(
    r"^[A-Za-z0-9_-]{1,256}$"
)


class TubeArchivistProvider(
    IntegrationProvider
):
    definition = ProviderDefinition(
        key="tubearchivist",
        label="TubeArchivist",
        description=(
            "Read metadata, catalog relationships, and artwork references "
            "from an existing TubeArchivist instance. LibraryForge never "
            "controls subscriptions, queues, downloads, or deletion."
        ),
        capabilities=(
            CAPABILITY_METADATA,
            CAPABILITY_ARTWORK,
            CAPABILITY_CATALOG,
        ),
        fields=(
            FieldDefinition(
                name="base_url",
                label="Server URL",
                placeholder=(
                    "https://tube.example.com"
                ),
                help_text=(
                    "Base URL of the TubeArchivist "
                    "web application."
                ),
            ),
            FieldDefinition(
                name="api_token",
                label="API token",
                secret=True,
                placeholder=(
                    "TubeArchivist API token"
                ),
                help_text=(
                    "Read-only LibraryForge requests "
                    "use TubeArchivist token authentication."
                ),
            ),
        ),
        online_video=True,
        storage_policy="transient",
        credential_mode=CREDENTIAL_USER,
        credential_summary=(
            "Use the URL and API token for your own TubeArchivist server. "
            "The token remains encrypted in LibraryForge."
        ),
    )

    def validate(self) -> None:
        super().validate()

        try:
            parsed = urlparse(
                self.base_url
            )
        except ValueError as exc:
            raise ValueError(
                "TubeArchivist Server URL is invalid."
            ) from exc

        if (
            parsed.scheme
            not in {
                "http",
                "https",
            }
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "TubeArchivist Server URL must be "
                "an http:// or https:// URL without "
                "embedded credentials, query, or fragment."
            )

    @property
    def base_url(self) -> str:
        return (
            str(
                self.configuration.get(
                    "base_url"
                )
                or ""
            )
            .strip()
            .rstrip("/")
            + "/"
        )

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": (
                "Token "
                + self.secrets.get(
                    "api_token",
                    "",
                ).strip()
            )
        }

    def _url(
        self,
        path: str,
    ) -> str:
        return urljoin(
            self.base_url,
            path.lstrip("/"),
        )

    def _get(
        self,
        path: str,
    ) -> Any:
        self.validate()

        return request_json(
            self._url(
                path
            ),
            headers=self.headers,
        )

    def test_connection(
        self,
    ) -> dict[str, Any]:
        payload = self._get(
            "api/video/"
        )

        count = 0

        if isinstance(
            payload,
            dict,
        ):
            data = payload.get(
                "data"
            )

            if isinstance(
                data,
                list,
            ):
                count = len(
                    data
                )

        return {
            "ok": True,
            "message": (
                "TubeArchivist API "
                "connection succeeded."
            ),
            "details": {
                "sample_video_count": count
            },
        }

    @staticmethod
    def _first_image_url(
        value: Any,
        *,
        hinted: bool = False,
    ) -> str:
        if isinstance(
            value,
            str,
        ):
            lowered = (
                value.lower()
            )

            if lowered.startswith(
                (
                    "http://",
                    "https://",
                    "/",
                )
            ):
                if (
                    hinted
                    or any(
                        suffix in lowered
                        for suffix in (
                            ".jpg",
                            ".jpeg",
                            ".png",
                            ".webp",
                        )
                    )
                ):
                    return value

            return ""

        if isinstance(
            value,
            list,
        ):
            for item in value:
                found = (
                    TubeArchivistProvider
                    ._first_image_url(
                        item,
                        hinted=hinted,
                    )
                )

                if found:
                    return found

            return ""

        if isinstance(
            value,
            dict,
        ):
            for (
                key,
                item,
            ) in value.items():
                if any(
                    hint
                    in str(
                        key
                    ).casefold()
                    for hint
                    in _IMAGE_KEY_HINTS
                ):
                    found = (
                        TubeArchivistProvider
                        ._first_image_url(
                            item,
                            hinted=True,
                        )
                    )

                    if found:
                        return found

            for item in value.values():
                found = (
                    TubeArchivistProvider
                    ._first_image_url(
                        item,
                        hinted=False,
                    )
                )

                if found:
                    return found

        return ""

    def _detail_path(
        self,
        target_type: str,
        source_id: str,
    ) -> str:
        source_id = str(
            source_id
            or ""
        ).strip()

        if not _SAFE_SOURCE_ID.fullmatch(
            source_id
        ):
            raise ValueError(
                "TubeArchivist source ID is invalid."
            )

        if target_type == "channel":
            return (
                f"api/channel/{source_id}/"
            )

        if target_type == "online_video":
            return (
                f"api/video/{source_id}/"
            )

        if target_type == "playlist":
            return (
                f"api/playlist/{source_id}/"
            )

        raise ValueError(
            "Unsupported TubeArchivist "
            f"target type: {target_type}"
        )

    def lookup_one(
        self,
        *,
        target_type: str,
        source_id: str,
    ) -> dict[str, Any] | None:
        payload = self._get(
            self._detail_path(
                target_type,
                source_id,
            )
        )

        if not isinstance(
            payload,
            dict,
        ):
            return None

        artwork = self._first_image_url(
            payload
        )

        if artwork.startswith(
            "/"
        ):
            artwork = self._url(
                artwork
            )

        return {
            "provider": "tubearchivist",
            "source_id": source_id,
            "artwork_url": artwork,
            "raw": payload,
        }

    def lookup_many(
        self,
        *,
        target_type: str,
        source_ids: list[str],
    ) -> dict[
        str,
        dict[str, Any],
    ]:
        output: dict[
            str,
            dict[str, Any],
        ] = {}

        for source_id in dict.fromkeys(
            source_ids
        ):
            if not source_id:
                continue

            try:
                item = self.lookup_one(
                    target_type=target_type,
                    source_id=source_id,
                )

            except ProviderHttpError:
                continue

            if item:
                output[
                    source_id
                ] = item

        return output
