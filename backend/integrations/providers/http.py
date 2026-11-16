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


MAX_RETRY_AFTER_SECONDS = 3600


class ProviderHttpError(
    RuntimeError
):
    """A sanitized provider transport failure.

    ``reason`` is one of ``http``, ``timeout``, ``unreachable``,
    ``too_large``, ``invalid_json`` or ``invalid_url`` so adapters can map
    failures to stable categories without parsing messages.
    """

    def __init__(
        self,
        message: str,
        status: int | None = None,
        *,
        reason: str = "http",
        retry_after: int | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.reason = reason
        self.retry_after = retry_after


def _retry_after_seconds(
    headers,
) -> int | None:
    # Only the delta-seconds form is honored; HTTP-date values are ignored.
    value = str(
        (headers or {}).get("Retry-After") or ""
    ).strip()
    if not value.isdigit():
        return None
    return min(
        int(value),
        MAX_RETRY_AFTER_SECONDS,
    )


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
    method: str = "GET",
    json_body: Any = None,
) -> Any:
    """Call a JSON API with GET or POST, optionally sending a JSON body.

    An empty response body, as from HTTP 204, returns None.
    """
    try:
        parsed = urlparse(
            url
        )
    except ValueError as exc:
        raise ProviderHttpError(
            "Remote service URL is invalid.",
            reason="invalid_url",
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
            "Remote service URL is invalid.",
            reason="invalid_url",
        )

    request_headers = {
        "Accept": "application/json",
        "User-Agent": "LibraryForge/0.1",
        **(headers or {}),
    }
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    request = Request(
        url,
        data=data,
        headers=request_headers,
        method=method.upper(),
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
            retry_after=_retry_after_seconds(
                exc.headers
            ),
        ) from exc

    except (
        URLError,
        TimeoutError,
        OSError,
    ) as exc:
        timed_out = isinstance(
            exc,
            TimeoutError,
        ) or isinstance(
            getattr(exc, "reason", None),
            TimeoutError,
        )
        raise ProviderHttpError(
            (
                "Remote service timed out."
                if timed_out
                else "Unable to reach remote service."
            ),
            reason=(
                "timeout"
                if timed_out
                else "unreachable"
            ),
        ) from exc

    if (
        len(body)
        > MAX_PROVIDER_JSON_BYTES
    ):
        raise ProviderHttpError(
            "Remote service response exceeded "
            "the 10 MB limit.",
            reason="too_large",
        )

    if not body.strip():
        return None

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
            "Remote service returned invalid JSON.",
            reason="invalid_json",
        ) from exc
