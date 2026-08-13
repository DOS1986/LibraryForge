import hashlib
import json

from django.conf import settings
from django.contrib.auth import (
    authenticate,
    login,
    logout,
)
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import (
    csrf_protect,
    ensure_csrf_cookie,
)
from django.views.decorators.http import (
    require_GET,
    require_POST,
)


MAX_AUTH_REQUEST_BYTES = 64 * 1024
MAX_EMAIL_LENGTH = 254
MAX_PASSWORD_LENGTH = 4096


def serialize_user(user):
    return {
        "id": user.pk,
        "email": user.email,
        "displayName": user.display_name,
        "firstName": user.first_name,
        "lastName": user.last_name,
        "isStaff": user.is_staff,
        "isSuperuser": user.is_superuser,
    }


def _client_ip(request) -> str:
    # Do not trust X-Forwarded-For here. If LibraryForge is behind a proxy,
    # REMOTE_ADDR is still a safe rate-limit bucket for the proxy itself.
    return str(
        request.META.get("REMOTE_ADDR")
        or "unknown"
    )


def _cache_key(prefix: str, *parts: str) -> str:
    payload = "\x00".join(parts).encode(
        "utf-8",
        errors="replace",
    )
    digest = hashlib.sha256(payload).hexdigest()
    return f"libraryforge:auth:{prefix}:{digest}"


def _count(key: str) -> int:
    try:
        return int(cache.get(key, 0) or 0)
    except Exception:
        # Authentication should not become unavailable because a cache
        # backend is temporarily unhealthy.
        return 0


def _increment(key: str, timeout: int) -> None:
    try:
        if cache.add(key, 1, timeout=timeout):
            return
        cache.incr(key)
    except Exception:
        # Rate limiting fails open if the cache backend itself fails.
        return


def _rate_limited_response(window_seconds: int):
    response = JsonResponse(
        {
            "detail": (
                "Too many failed sign-in attempts. "
                "Try again later."
            )
        },
        status=429,
    )
    response["Retry-After"] = str(
        max(1, window_seconds)
    )
    return response


@require_GET
@ensure_csrf_cookie
@never_cache
def csrf_token(request):
    return JsonResponse(
        {
            "detail": "CSRF cookie set."
        }
    )


@require_GET
@never_cache
def current_user(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {
                "detail": "Authentication required."
            },
            status=401,
        )

    return JsonResponse(
        {
            "user": serialize_user(
                request.user
            )
        }
    )


@require_POST
@csrf_protect
@never_cache
def login_view(request):
    content_length = request.META.get(
        "CONTENT_LENGTH"
    )

    try:
        if (
            content_length
            and int(content_length)
            > MAX_AUTH_REQUEST_BYTES
        ):
            return JsonResponse(
                {
                    "detail": "Request body is too large."
                },
                status=413,
            )
    except (TypeError, ValueError):
        pass

    try:
        payload = json.loads(
            request.body
            or b"{}"
        )
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "detail": "Invalid JSON."
            },
            status=400,
        )

    if not isinstance(payload, dict):
        return JsonResponse(
            {
                "detail": "Invalid JSON object."
            },
            status=400,
        )

    email = str(
        payload.get(
            "email",
            "",
        )
        or ""
    ).strip()

    password = str(
        payload.get(
            "password",
            "",
        )
        or ""
    )

    if (
        not email
        or not password
        or len(email) > MAX_EMAIL_LENGTH
        or len(password) > MAX_PASSWORD_LENGTH
    ):
        return JsonResponse(
            {
                "detail": (
                    "Email and password are required."
                )
            },
            status=400,
        )

    window_seconds = max(
        30,
        int(
            getattr(
                settings,
                "LIBRARYFORGE_LOGIN_WINDOW_SECONDS",
                300,
            )
        ),
    )

    pair_limit = max(
        1,
        int(
            getattr(
                settings,
                "LIBRARYFORGE_LOGIN_MAX_FAILURES",
                8,
            )
        ),
    )

    ip_limit = max(
        pair_limit,
        int(
            getattr(
                settings,
                "LIBRARYFORGE_LOGIN_IP_MAX_FAILURES",
                40,
            )
        ),
    )

    client_ip = _client_ip(request)

    pair_key = _cache_key(
        "pair",
        client_ip,
        email.casefold(),
    )

    ip_key = _cache_key(
        "ip",
        client_ip,
    )

    if (
        _count(pair_key) >= pair_limit
        or _count(ip_key) >= ip_limit
    ):
        return _rate_limited_response(
            window_seconds
        )

    user = authenticate(
        request,
        username=email,
        password=password,
    )

    if user is None:
        _increment(
            pair_key,
            window_seconds,
        )
        _increment(
            ip_key,
            window_seconds,
        )

        return JsonResponse(
            {
                "detail": (
                    "Invalid email or password."
                )
            },
            status=401,
        )

    try:
        cache.delete(pair_key)
    except Exception:
        pass

    login(
        request,
        user,
    )

    return JsonResponse(
        {
            "user": serialize_user(
                user
            )
        }
    )


@require_POST
@csrf_protect
@never_cache
def logout_view(request):
    logout(request)

    return JsonResponse(
        {
            "detail": "Signed out."
        }
    )
