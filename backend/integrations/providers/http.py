from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ProviderHttpError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def request_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 8.0,
) -> Any:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "LibraryForge/0.1",
            **(headers or {}),
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
    except HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        raise ProviderHttpError(
            f"Remote service returned HTTP {exc.code}. {detail}".strip(),
            status=exc.code,
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ProviderHttpError(f"Unable to reach remote service: {exc}") from exc

    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderHttpError("Remote service returned invalid JSON.") from exc
