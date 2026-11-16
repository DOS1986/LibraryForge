import os
from pathlib import Path, PurePosixPath

from django.conf import settings


class ProjectionSecurityError(ValueError):
    """A projection folder or source that isn't allowed. ``message`` is
    LibraryForge's own explanation, safe to show to the user."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


NO_OUTPUT_ROOTS = (
    "No output folders are allowed yet. Set LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS on the LibraryForge server "
    "to the folder(s) projections may write into, then restart it."
)
OUTSIDE_OUTPUT_ROOTS = "Projection destination is outside the output folders allowed by LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS."


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


def _output_root_settings() -> list[str]:
    return [str(value).strip() for value in getattr(settings, "LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS", []) if str(value).strip()]


def _folder_key(value: str) -> str:
    """An absolute, normalized form of ``value`` ending in a separator, worked
    out from the text alone, without touching the disk."""

    return os.path.join(os.path.normcase(os.path.normpath(os.path.abspath(os.path.expanduser(value)))), "")


def confined_output_folder(destination_path: str) -> Path:
    """The real path of ``destination_path`` if it's inside an allowed output
    root, else ``ProjectionSecurityError``.

    The text is checked against the roots before the disk is touched, so a
    path elsewhere (another computer's share, say) is never looked up. The
    real path, with links followed, is then checked again, so a link inside
    a root can't lead out of it. Every use of a projection folder goes
    through here first.
    """

    if not str(destination_path or "").strip():
        raise ProjectionSecurityError("Projection destination path is required.")
    roots = _output_root_settings()
    if not roots:
        raise ProjectionSecurityError(NO_OUTPUT_ROOTS)
    key = _folder_key(str(destination_path))
    if not any(key.startswith(_folder_key(root)) for root in roots):
        raise ProjectionSecurityError(OUTSIDE_OUTPUT_ROOTS)

    # The real path spells every existing folder the way the disk does
    # (Windows letter case included), so the comparison is exact. This is the
    # function's only way out with a path.
    folder = os.path.realpath(os.path.expanduser(str(destination_path)))
    for root in roots:
        real_root = os.path.realpath(os.path.expanduser(root)).rstrip("\\/")
        if folder.startswith(real_root) and folder[len(real_root) : len(real_root) + 1] in ("", "\\", "/"):
            return Path(folder)
    raise ProjectionSecurityError(OUTSIDE_OUTPUT_ROOTS)


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

    # In-place NFO output writes into its own library and has no output folder.
    for projection in Projection.objects.exclude(layout=Projection.Layout.LIBRARY_NFO).only("id", "name", "destination_path"):
        try:
            destination = confined_output_folder(projection.destination_path)
        except (OSError, ValueError):
            # Outside every output root, so it can't be written to anyway.
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

    destination = confined_output_folder(destination_path)

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
