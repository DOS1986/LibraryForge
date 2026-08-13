from __future__ import annotations

import json
from typing import Any
from urllib.error import (
    HTTPError,
    URLError,
)
from urllib.parse import urlparse
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
)


MAX_PROVIDER_JSON_BYTES = (
    10 * 1024 * 1024
)


class ProviderHttpError(
    RuntimeError
):
    def __init__(
        self,
        message: str,
        status: int | None = None,
    ):
        super().__init__(message)
        self.status = status


class _NoRedirectHandler(
    HTTPRedirectHandler
):
    def redirect_request(
        self,
        req,
        fp,
        code,
        msg,
        headers,
        newurl,
    ):
        # Provider credentials must never be forwarded to a redirect
        # target. Configure provider base URLs to their final origin.
        return None


def request_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 8.0,
) -> Any:
    try:
        parsed = urlparse(
            url
        )
    except ValueError as exc:
        raise ProviderHttpError(
            "Remote service URL is invalid."
        ) from exc

    if (
        parsed.scheme not in {
            "http",
            "https",
        }
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ProviderHttpError(
            "Remote service URL is invalid."
        )

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "LibraryForge/0.1",
            **(headers or {}),
        },
        method="GET",
    )

    opener = build_opener(
        _NoRedirectHandler()
    )

    try:
        with opener.open(
            request,
            timeout=timeout,
        ) as response:
            body = response.read(
                MAX_PROVIDER_JSON_BYTES
                + 1
            )

    except HTTPError as exc:
        # Do not echo remote response bodies. They can contain reflected
        # request data, internal service details, or provider credentials.
        raise ProviderHttpError(
            (
                "Remote service returned "
                f"HTTP {exc.code}."
            ),
            status=exc.code,
        ) from exc

    except (
        URLError,
        TimeoutError,
        OSError,
    ) as exc:
        raise ProviderHttpError(
            "Unable to reach remote service."
        ) from exc

    if (
        len(body)
        > MAX_PROVIDER_JSON_BYTES
    ):
        raise ProviderHttpError(
            "Remote service response exceeded "
            "the 10 MB limit."
        )

    try:
        return json.loads(
            body.decode(
                "utf-8"
            )
        )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ProviderHttpError(
            "Remote service returned invalid JSON."
        ) from exc
