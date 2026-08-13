from pathlib import Path

from django.conf import settings


class LibraryPathPolicyError(ValueError):
    pass


def _resolved(path: Path) -> Path:
    try:
        return path.expanduser().resolve(
            strict=True
        )
    except OSError:
        return path.expanduser().resolve(
            strict=False
        )


def _inside(
    candidate: Path,
    root: Path,
) -> bool:
    try:
        return (
            candidate == root
            or candidate.is_relative_to(root)
        )
    except ValueError:
        return False


def enforce_library_path_policy(
    *,
    path: Path,
    user,
) -> Path:
    candidate = _resolved(path)

    configured_roots = [
        _resolved(
            Path(value)
        )
        for value in getattr(
            settings,
            "LIBRARYFORGE_ALLOWED_LIBRARY_ROOTS",
            [],
        )
        if str(value).strip()
    ]

    if configured_roots:
        if not any(
            _inside(
                candidate,
                root,
            )
            for root in configured_roots
        ):
            raise LibraryPathPolicyError(
                "This path is outside the library roots "
                "allowed by the LibraryForge server."
            )

        return candidate

    if settings.DEBUG:
        return candidate

    if not (
        getattr(
            user,
            "is_staff",
            False,
        )
        or getattr(
            user,
            "is_superuser",
            False,
        )
    ):
        raise LibraryPathPolicyError(
            "The server operator has not configured "
            "LIBRARYFORGE_ALLOWED_LIBRARY_ROOTS. "
            "Only staff users may select arbitrary "
            "server paths until an allowlist is configured."
        )

    return candidate
