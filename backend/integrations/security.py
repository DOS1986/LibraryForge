from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from urllib.error import (
    HTTPError,
    URLError,
)
from urllib.parse import (
    urljoin,
    urlparse,
)
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
)

from integrations.providers.http import (
    ProviderHttpError,
)


PUBLIC_IMAGE_HOST_SUFFIXES = (
    "ytimg.com",
    "ggpht.com",
    "googleusercontent.com",
)

MAX_ARTWORK_REDIRECTS = 3

_REDIRECT_STATUSES = {
    301,
    302,
    303,
    307,
    308,
}


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
        # Redirects are handled explicitly in fetch_remote_artwork so every
        # redirect target is revalidated and credentials are recalculated for
        # the new origin.
        return None


@dataclass(frozen=True)
class RemoteImage:
    body: bytes
    content_type: str


def _origin(parsed):
    scheme = (
        parsed.scheme
        or ""
    ).casefold()

    hostname = (
        parsed.hostname
        or ""
    ).casefold()

    if not scheme or not hostname:
        return None

    if parsed.username or parsed.password:
        return None

    try:
        if parsed.port is not None:
            port = parsed.port
        elif scheme == "https":
            port = 443
        elif scheme == "http":
            port = 80
        else:
            return None

    except ValueError:
        return None

    return (
        scheme,
        hostname,
        port,
    )


def _public_image_host_allowed(
    hostname: str,
) -> bool:
    hostname = (
        hostname
        or ""
    ).casefold()

    return any(
        hostname == suffix
        or hostname.endswith(
            "." + suffix
        )
        for suffix in PUBLIC_IMAGE_HOST_SUFFIXES
    )


def _provider_base_origin(
    provider,
    connection_provider: str,
):
    if connection_provider != "tubearchivist":
        return None

    try:
        return _origin(
            urlparse(
                getattr(
                    provider,
                    "base_url",
                    "",
                )
            )
        )
    except ValueError:
        return None


def allowed_artwork_url(
    *,
    artwork_url: str,
    provider,
    connection_provider: str,
) -> bool:
    try:
        parsed = urlparse(
            artwork_url
        )
        origin = _origin(
            parsed
        )
    except ValueError:
        return False

    if origin is None:
        return False

    scheme, hostname, _port = origin

    if _public_image_host_allowed(
        hostname
    ):
        # Public YouTube/Google artwork must use TLS.
        return scheme == "https"

    provider_origin = _provider_base_origin(
        provider,
        connection_provider,
    )

    if provider_origin is not None:
        # Private/self-hosted artwork may be fetched only from the exact
        # configured TubeArchivist origin.
        return origin == provider_origin

    return False


def _headers_for_artwork_url(
    *,
    artwork_url: str,
    provider,
    connection_provider: str,
) -> dict[str, str]:
    headers = {
        "User-Agent": "LibraryForge/0.1",
    }

    # CRITICAL: TubeArchivist credentials are attached only when the request
    # is going to the exact configured TubeArchivist origin. They are never
    # sent to ytimg.com, ggpht.com, googleusercontent.com, or a redirect target
    # on a different origin.
    if connection_provider != "tubearchivist":
        return headers

    try:
        artwork_origin = _origin(
            urlparse(
                artwork_url
            )
        )
    except ValueError:
        return headers

    provider_origin = _provider_base_origin(
        provider,
        connection_provider,
    )

    if (
        artwork_origin is not None
        and provider_origin is not None
        and artwork_origin == provider_origin
    ):
        headers.update(
            getattr(
                provider,
                "headers",
                {},
            )
        )

    return headers


def fetch_remote_artwork(
    *,
    artwork_url: str,
    provider,
    connection_provider: str,
    max_bytes: int,
    timeout: float = 10.0,
) -> RemoteImage | None:
    current_url = str(
        artwork_url
        or ""
    ).strip()

    if not current_url:
        return None

    opener = build_opener(
        _NoRedirectHandler()
    )

    for redirect_count in range(
        MAX_ARTWORK_REDIRECTS + 1
    ):
        if not allowed_artwork_url(
            artwork_url=current_url,
            provider=provider,
            connection_provider=connection_provider,
        ):
            return None

        headers = _headers_for_artwork_url(
            artwork_url=current_url,
            provider=provider,
            connection_provider=connection_provider,
        )

        request = Request(
            current_url,
            headers=headers,
            method="GET",
        )

        try:
            with opener.open(
                request,
                timeout=timeout,
            ) as response:
                body = response.read(
                    max_bytes + 1
                )

                content_type = (
                    response.headers
                    .get_content_type()
                )

        except HTTPError as exc:
            if (
                exc.code in _REDIRECT_STATUSES
                and redirect_count
                < MAX_ARTWORK_REDIRECTS
            ):
                location = (
                    exc.headers.get(
                        "Location"
                    )
                    if exc.headers
                    else None
                )

                if not location:
                    return None

                next_url = urljoin(
                    current_url,
                    location,
                )

                if not allowed_artwork_url(
                    artwork_url=next_url,
                    provider=provider,
                    connection_provider=connection_provider,
                ):
                    return None

                current_url = next_url
                continue

            return None

        except (
            URLError,
            TimeoutError,
            OSError,
            ValueError,
        ):
            return None

        if len(body) > max_bytes:
            return None

        if not content_type.startswith(
            "image/"
        ):
            guessed = (
                mimetypes.guess_type(
                    current_url
                )[0]
                or ""
            )

            if not guessed.startswith(
                "image/"
            ):
                return None

            content_type = guessed

        return RemoteImage(
            body=body,
            content_type=content_type,
        )

    return None


def public_provider_error(
    exc: Exception,
) -> str:
    if isinstance(
        exc,
        ProviderHttpError,
    ):
        if exc.status is not None:
            return (
                "Provider request failed "
                f"with HTTP {exc.status}."
            )

        return (
            "Provider request failed because "
            "the remote service was unavailable."
        )

    if isinstance(
        exc,
        ValueError,
    ):
        # Provider validation errors are authored by LibraryForge and should
        # not contain request headers or encrypted secret payloads.
        return str(exc)

    return "Integration request failed."