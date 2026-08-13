import json
import os
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import logout as django_logout
from django.db import connection
from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import (
    api_view,
    permission_classes,
)
from rest_framework.permissions import (
    AllowAny,
    IsAuthenticated,
)
from rest_framework.response import Response

from libraryforge.versioning import get_version_info
from preferences.models import SystemAction


def _environment_name():
    return (
        "development"
        if settings.DEBUG
        else "production"
    )


def _is_admin(user) -> bool:
    return bool(
        user.is_staff
        or user.is_superuser
    )


def _restart_enabled():
    return bool(
        getattr(
            settings,
            "LIBRARYFORGE_RESTART_ENABLED",
            False,
        )
    )


def _restart_file():
    configured = getattr(
        settings,
        "LIBRARYFORGE_RESTART_FILE",
        "",
    )

    if configured:
        return Path(configured)

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

    except Exception:
        # Do not return database driver errors, hostnames, credentials,
        # filesystem paths, or SQL details to the browser.
        return {
            "status": "error",
            "detail": "Database connection unavailable.",
        }


def _ffprobe_status(
    *,
    include_paths: bool,
):
    configured = str(
        getattr(
            settings,
            "FFPROBE_PATH",
            "ffprobe",
        )
    )

    resolved = shutil.which(
        configured
    )

    try:
        if (
            not resolved
            and Path(configured).is_file()
        ):
            resolved = str(
                Path(configured).resolve()
            )
    except OSError:
        resolved = None

    result = {
        "status": (
            "ok"
            if resolved
            else "missing"
        ),
    }

    if include_paths:
        result["configured_path"] = configured
        result["resolved_path"] = resolved

    return result


def _write_restart_request(
    restart_file: Path,
    payload: dict,
):
    restart_file = restart_file.expanduser()

    restart_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if restart_file.exists() and restart_file.is_dir():
        raise OSError(
            "Restart request path is a directory."
        )

    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=".libraryforge-restart-",
            suffix=".tmp",
            dir=restart_file.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(
                temporary.name
            )

            json.dump(
                payload,
                temporary,
                indent=2,
            )
            temporary.write("\n")
            temporary.flush()

            try:
                os.fsync(
                    temporary.fileno()
                )
            except OSError:
                pass

        if (
            temporary_path
            and os.name != "nt"
        ):
            try:
                os.chmod(
                    temporary_path,
                    0o600,
                )
            except OSError:
                pass

        os.replace(
            temporary_path,
            restart_file,
        )

        temporary_path = None

    finally:
        if temporary_path:
            try:
                temporary_path.unlink(
                    missing_ok=True
                )
            except OSError:
                pass


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

    admin_user = _is_admin(
        request.user
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
            "ffprobe": _ffprobe_status(
                include_paths=(
                    admin_user
                    and settings.DEBUG
                )
            ),
            "restart": {
                "supported": (
                    _restart_enabled()
                    if admin_user
                    else False
                ),
                "request_file": (
                    str(_restart_file())
                    if (
                        admin_user
                        and settings.DEBUG
                    )
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
                    if (
                        last_restart
                        and admin_user
                    )
                    else None
                ),
            },
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def system_restart(request):
    if not _is_admin(
        request.user
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

    request_payload = {
        "requested_at": (
            timezone.now().isoformat()
        ),
        "requested_by": (
            request.user.pk
        ),
        "runtime_started_at": version[
            "runtime_started_at"
        ],
    }

    try:
        _write_restart_request(
            _restart_file(),
            request_payload,
        )
    except OSError:
        return Response(
            {
                "detail": (
                    "LibraryForge could not create the "
                    "restart request signal."
                )
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    SystemAction.objects.create(
        actor=request.user,
        action=SystemAction.Action.RESTART,
        metadata={
            "runtime_started_at": version[
                "runtime_started_at"
            ],
        },
    )

    # Only the requesting administrator is signed out.
    django_logout(
        request._request
    )

    return Response(
        {
            "accepted": True,
            "runtime_started_at": version[
                "runtime_started_at"
            ],
        },
        status=status.HTTP_202_ACCEPTED,
    )
