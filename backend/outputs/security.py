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


def overlapping_library(destination: Path):
    """A library whose folder contains, or sits inside, ``destination``."""

    from libraries.models import Library

    for library in Library.objects.all().only("id", "name", "path"):
        try:
            root = _resolve(library.path)
        except (OSError, ValueError):
            continue
        if _inside(destination, root) or _inside(root, destination):
            return library
    return None


def overlapping_projection(path: Path):
    """A projection whose output folder contains, or sits inside, ``path``."""

    from outputs.models import Projection

    for projection in Projection.objects.all().only("id", "name", "destination_path"):
        try:
            destination = _resolve(projection.destination_path)
        except (OSError, ValueError):
            continue
        if _inside(path, destination) or _inside(destination, path):
            return projection
    return None


def validate_projection_destination(
    *,
    library,
    destination_path: str,
    user,
) -> Path:
    """The destination must be inside an allowed output root (required for
    everyone, development included) and separate from every library."""

    if not str(destination_path or "").strip():
        raise ProjectionSecurityError("Projection destination path is required.")
    destination = _resolve(destination_path)

    configured_roots = [
        _resolve(value)
        for value in getattr(settings, "LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS", [])
        if str(value).strip()
    ]
    if not configured_roots:
        raise ProjectionSecurityError(
            "No output folders are allowed yet. Set LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS on the LibraryForge server "
            "to the folder(s) projections may write into, then restart it."
        )
    if not any(_inside(destination, root) for root in configured_roots):
        raise ProjectionSecurityError(
            "Projection destination is outside the output folders allowed by LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS."
        )

    # Output and libraries must be disjoint in both directions, for every
    # library: scanning output would create duplicates, and a broad output
    # folder must never render into a source tree.
    clash = overlapping_library(destination)
    if clash is not None:
        raise ProjectionSecurityError(
            f'Projection output must be separate from every library folder; it overlaps the "{clash.name}" library.'
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
