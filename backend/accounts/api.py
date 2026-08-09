import json

from django.contrib.auth import (
    authenticate,
    login,
    logout,
)

from django.http import JsonResponse

from django.views.decorators.csrf import (
    csrf_protect,
    ensure_csrf_cookie,
)

from django.views.decorators.http import (
    require_GET,
    require_POST,
)


def serialize_user(user):
    return {
        "id": user.pk,
        "email": user.email,
        "displayName":
            user.display_name,
        "firstName":
            user.first_name,
        "lastName":
            user.last_name,
        "isStaff":
            user.is_staff,
        "isSuperuser":
            user.is_superuser,
    }


@require_GET
@ensure_csrf_cookie
def csrf_token(request):
    return JsonResponse(
        {
            "detail":
                "CSRF cookie set."
        }
    )


@require_GET
def current_user(request):
    if not (
        request.user
        .is_authenticated
    ):
        return JsonResponse(
            {
                "detail":
                    "Authentication required."
            },
            status=401,
        )

    return JsonResponse(
        {
            "user":
                serialize_user(
                    request.user
                )
        }
    )


@require_POST
@csrf_protect
def login_view(request):
    try:
        payload = json.loads(
            request.body
            or "{}"
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {
                "detail":
                    "Invalid JSON."
            },
            status=400,
        )

    email = (
        payload
        .get(
            "email",
            "",
        )
        .strip()
    )

    password = payload.get(
        "password",
        "",
    )

    if not email or not password:
        return JsonResponse(
            {
                "detail":
                    "Email and password "
                    "are required."
            },
            status=400,
        )

    user = authenticate(
        request,
        username=email,
        password=password,
    )

    if user is None:
        return JsonResponse(
            {
                "detail":
                    "Invalid email "
                    "or password."
            },
            status=401,
        )

    login(
        request,
        user,
    )

    return JsonResponse(
        {
            "user":
                serialize_user(
                    user
                )
        }
    )


@require_POST
@csrf_protect
def logout_view(request):
    logout(
        request
    )

    return JsonResponse(
        {
            "detail":
                "Signed out."
        }
    )