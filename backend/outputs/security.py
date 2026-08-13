from pathlib import Path, PurePosixPath

from django.conf import settings


class ProjectionSecurityError(ValueError):
    pass


def _resolve(
    value: str | Path,
) -> Path:
    return (
        Path(value)
        .expanduser()
        .resolve(
            strict=False
        )
    )


def _inside(
    candidate: Path,
    root: Path,
) -> bool:
    try:
        return (
            candidate == root
            or candidate.is_relative_to(
                root
            )
        )
    except ValueError:
        return False


def validate_projection_destination(
    *,
    library,
    destination_path: str,
    user,
) -> Path:
    if not str(
        destination_path
        or ""
    ).strip():
        raise ProjectionSecurityError(
            "Projection destination path is required."
        )

    destination = _resolve(
        destination_path
    )

    source_root = _resolve(
        library.path
    )

    # Projection output and source library roots must be disjoint.
    # Blocking both directions prevents a broad destination root from
    # accidentally rendering a path back into the source library.
    if (
        _inside(
            destination,
            source_root,
        )
        or _inside(
            source_root,
            destination,
        )
    ):
        raise ProjectionSecurityError(
            "Projection output must be separate "
            "from the source library tree."
        )

    configured_roots = [
        _resolve(
            value
        )
        for value in getattr(
            settings,
            "LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS",
            [],
        )
        if str(value).strip()
    ]

    if configured_roots:
        if not any(
            _inside(
                destination,
                root,
            )
            for root in configured_roots
        ):
            raise ProjectionSecurityError(
                "Projection destination is outside "
                "the output roots allowed by the "
                "LibraryForge server."
            )

        return destination

    if settings.DEBUG:
        return destination

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
        raise ProjectionSecurityError(
            "The server operator has not configured "
            "LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS. "
            "Only staff users may select arbitrary "
            "projection destinations until an "
            "allowlist is configured."
        )

    return destination


def validate_projection_sources(
    *,
    projection,
) -> None:
    root = _resolve(
        projection.library.path
    )

    relative_paths = (
        projection.library
        .media_files
        .filter(
            is_present=True
        )
        .values_list(
            "relative_path",
            flat=True,
        )
    )

    for value in relative_paths:
        normalized = str(
            value
            or ""
        ).replace(
            "\\",
            "/",
        )

        relative = PurePosixPath(
            normalized
        )

        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not relative.parts
        ):
            raise ProjectionSecurityError(
                "Projection contains an invalid "
                "source media path."
            )

        source = (
            root.joinpath(
                *relative.parts
            )
            .resolve(
                strict=False
            )
        )

        if not _inside(
            source,
            root,
        ):
            raise ProjectionSecurityError(
                "Projection source media escaped "
                "the configured library root."
            )


def validate_projection_for_run(
    *,
    projection,
    user,
) -> None:
    validate_projection_destination(
        library=projection.library,
        destination_path=(
            projection.destination_path
        ),
        user=user,
    )

    validate_projection_sources(
        projection=projection
    )
