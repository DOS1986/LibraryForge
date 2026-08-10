import json
import os
import shutil
from pathlib import Path

from django.conf import settings
from django.contrib.auth import logout as django_logout
from django.db import connection
from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from libraryforge.versioning import get_version_info
from preferences.models import SystemAction


def _environment_name():
    return "development" if settings.DEBUG else "production"


def _restart_enabled():
    configured = getattr(
        settings,
        "LIBRARYFORGE_RESTART_ENABLED",
        None,
    )

    if configured is not None:
        return bool(configured)

    return os.environ.get(
        "LIBRARYFORGE_RESTART_ENABLED",
        "false",
    ).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _restart_file():
    configured = getattr(
        settings,
        "LIBRARYFORGE_RESTART_FILE",
        None,
    )

    if configured:
        return Path(configured)

    environment_value = os.environ.get(
        "LIBRARYFORGE_RESTART_FILE"
    )

    if environment_value:
        return Path(environment_value)

    return (
        Path(settings.BASE_DIR).parent
        / "runtime"
        / "restart.request"
    )


def _database_status():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

        return {
            "status": "ok",
            "detail": "Connected",
        }

    except Exception as exc:  # pragma: no cover - environment failure
        return {
            "status": "error",
            "detail": str(exc),
        }


def _ffprobe_status():
    configured = os.environ.get(
        "FFPROBE_PATH",
        "ffprobe",
    )

    resolved = shutil.which(configured)

    if not resolved and Path(configured).is_file():
        resolved = str(Path(configured).resolve())

    return {
        "status": "ok" if resolved else "missing",
        "configured_path": configured,
        "resolved_path": resolved,
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def system_version(request):
    return Response(
        get_version_info(
            environment=_environment_name()
        )
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def system_health(request):
    version = get_version_info(
        environment=_environment_name()
    )

    return Response(
        {
            "status": "ok",
            "version": version["version"],
            "runtime_started_at": version[
                "runtime_started_at"
            ],
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def system_status(request):
    version = get_version_info(
        environment=_environment_name()
    )

    last_restart = (
        SystemAction.objects
        .filter(
            action=SystemAction.Action.RESTART
        )
        .select_related("actor")
        .first()
    )

    return Response(
        {
            "status": "ok",
            "version": version,
            "database": _database_status(),
            "ffprobe": _ffprobe_status(),
            "restart": {
                "supported": _restart_enabled(),
                "request_file": (
                    str(_restart_file())
                    if settings.DEBUG
                    else None
                ),
                "last_requested_at": (
                    last_restart.created_at.isoformat()
                    if last_restart
                    else None
                ),
                "last_requested_by": (
                    getattr(
                        last_restart.actor,
                        "email",
                        None,
                    )
                    if last_restart
                    else None
                ),
            },
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def system_restart(request):
    if not (
        request.user.is_staff
        or request.user.is_superuser
    ):
        return Response(
            {
                "detail": (
                    "Only a staff or superuser account "
                    "may restart LibraryForge."
                )
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    if not _restart_enabled():
        return Response(
            {
                "detail": (
                    "Application restart is not enabled "
                    "for this LibraryForge runtime. Start "
                    "development with scripts/dev.ps1 on Windows "
                    "or scripts/dev.sh on Linux/macOS, or "
                    "configure a production supervisor."
                )
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    version = get_version_info(
        environment=_environment_name()
    )

    restart_file = _restart_file()
    restart_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    request_payload = {
        "requested_at": timezone.now().isoformat(),
        "requested_by": request.user.pk,
        "requested_by_email": getattr(
            request.user,
            "email",
            "",
        ),
        "runtime_started_at": version[
            "runtime_started_at"
        ],
    }

    temporary_file = restart_file.with_suffix(
        restart_file.suffix + ".tmp"
    )

    temporary_file.write_text(
        json.dumps(
            request_payload,
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary_file.replace(restart_file)

    SystemAction.objects.create(
        actor=request.user,
        action=SystemAction.Action.RESTART,
        metadata={
            "runtime_started_at": version[
                "runtime_started_at"
            ],
        },
    )

    # The administrator who requested a restart should return to the
    # login screen after the new runtime is available. Other users keep
    # their sessions.
    django_logout(request._request)

    return Response(
        {
            "accepted": True,
            "runtime_started_at": version[
                "runtime_started_at"
            ],
        },
        status=status.HTTP_202_ACCEPTED,
    )
