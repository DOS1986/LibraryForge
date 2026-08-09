from __future__ import annotations

import os
import platform
import subprocess
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import django


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VERSION_FILE = PROJECT_ROOT / "VERSION"
BACKEND_PYPROJECT = PROJECT_ROOT / "backend" / "pyproject.toml"

RUNTIME_STARTED_AT = datetime.now(
    UTC
).isoformat()


def _environment_value(
    name: str,
):
    value = os.getenv(
        name,
        "",
    ).strip()

    return value or None


def read_app_version() -> str:
    override = _environment_value(
        "LIBRARYFORGE_VERSION"
    )

    if override:
        return override

    try:
        return (
            VERSION_FILE
            .read_text(
                encoding="utf-8"
            )
            .strip()
        )

    except OSError:
        return "0.0.0-unknown"


def read_backend_package_version() -> str | None:
    try:
        with BACKEND_PYPROJECT.open(
            "rb"
        ) as file:
            data = tomllib.load(
                file
            )

    except (
        OSError,
        tomllib.TOMLDecodeError,
    ):
        return None

    project = data.get(
        "project",
        {},
    )

    value = project.get(
        "version"
    )

    return (
        value
        if isinstance(
            value,
            str,
        )
        else None
    )


def _git_command(
    *args: str,
) -> str | None:
    try:
        result = subprocess.run(
            [
                "git",
                *args,
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            check=True,
            text=True,
            timeout=2,
        )

    except (
        OSError,
        subprocess.SubprocessError,
    ):
        return None

    value = result.stdout.strip()

    return value or None


def get_git_sha() -> str | None:
    return (
        _environment_value(
            "LIBRARYFORGE_GIT_SHA"
        )
        or _git_command(
            "rev-parse",
            "HEAD",
        )
    )


def get_git_branch() -> str | None:
    return (
        _environment_value(
            "LIBRARYFORGE_GIT_BRANCH"
        )
        or _git_command(
            "rev-parse",
            "--abbrev-ref",
            "HEAD",
        )
    )


def get_git_dirty() -> bool | None:
    override = _environment_value(
        "LIBRARYFORGE_GIT_DIRTY"
    )

    if override is not None:
        return (
            override.lower()
            in {
                "1",
                "true",
                "yes",
            }
        )

    status = _git_command(
        "status",
        "--porcelain",
    )

    if status is None:
        return None

    return bool(
        status
    )


def get_version_info(
    *,
    environment: str,
):
    version = read_app_version()

    package_version = (
        read_backend_package_version()
    )

    git_sha = get_git_sha()

    return {
        "name":
            "LibraryForge",

        "version":
            version,

        "channel":
            (
                "development"
                if "-"
                in version
                else "stable"
            ),

        "environment":
            environment,

        "backend_package_version":
            package_version,

        "backend_version_consistent":
            (
                package_version
                is None
                or package_version
                == version
            ),

        "git_sha":
            git_sha,

        "git_short_sha":
            (
                git_sha[:8]
                if git_sha
                else None
            ),

        "git_branch":
            get_git_branch(),

        "git_dirty":
            get_git_dirty(),

        "build_time":
            _environment_value(
                "LIBRARYFORGE_BUILD_TIME"
            ),

        "runtime_started_at":
            RUNTIME_STARTED_AT,

        "python_version":
            platform.python_version(),

        "django_version":
            django.get_version(),
    }
