import os
import tempfile
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.utils import timezone

from libraries.models import Library
from metadata.models import NfoFile
from metadata.services.nfo import (
    parse_nfo_content as _parse_nfo_content,
)


def _max_nfo_bytes() -> int:
    return max(
        1024,
        int(
            getattr(
                settings,
                "LIBRARYFORGE_MAX_NFO_BYTES",
                10 * 1024 * 1024,
            )
        ),
    )


def _validate_raw_xml(
    raw_xml: str,
):
    encoded_size = len(
        raw_xml.encode(
            "utf-8",
            errors="strict",
        )
    )

    if encoded_size > _max_nfo_bytes():
        raise ValueError(
            "NFO content exceeds the configured "
            "inspection/write limit."
        )

    lowered = raw_xml.casefold()

    # Kodi-style NFOs do not require DTD declarations or custom entities.
    # Reject them before ElementTree sees the document so entity-expansion
    # payloads and external-entity syntax are never accepted by the API.
    if (
        "<!doctype" in lowered
        or "<!entity" in lowered
    ):
        raise ValueError(
            "DTD and ENTITY declarations are not allowed in NFO files."
        )


def parse_nfo_content(
    raw_xml: str,
):
    text = str(
        raw_xml
        or ""
    )

    try:
        _validate_raw_xml(
            text
        )
    except ValueError as exc:
        return {
            "status":
                NfoFile.ParseStatus.ERROR,
            "root_element":
                "",
            "title":
                "",
            "year":
                None,
            "parsed_data":
                {},
            "error":
                str(exc),
        }

    return _parse_nfo_content(
        text
    )


def library_root_problem(
    exc: OSError,
) -> str:
    """A plain explanation of why a library folder can't be reached."""

    if getattr(exc, "winerror", None) in (1326, 86, 1244, 5):
        return (
            "The library folder can't be reached: the computer running LibraryForge "
            "isn't signed in to that network share (Windows reports: "
            f"{exc.strerror or 'access denied'}). Sign in to the share and save "
            "the credentials, then try again."
        )
    reason = exc.strerror or "it isn't available"
    return f"The library folder can't be reached ({reason})."


def library_root_error(
    library,
) -> str | None:
    """None if the library's root folder is reachable, else why not."""

    try:
        root = Path(library.path).expanduser().resolve(strict=True)
        if not root.is_dir():
            return "The library folder can't be reached (it isn't a folder)."
    except OSError as exc:
        return library_root_problem(exc)
    return None


def _destination_for(
    nfo_file: NfoFile,
) -> Path:
    relative_value = str(
        nfo_file.relative_path
        or ""
    ).replace(
        "\\",
        "/",
    )

    relative = PurePosixPath(
        relative_value
    )

    if (
        relative.is_absolute()
        or ".." in relative.parts
        or not relative.parts
    ):
        raise PermissionError(
            "NFO path is outside the configured library root."
        )

    if relative.suffix.casefold() != ".nfo":
        raise PermissionError(
            "Only indexed .nfo files may be written."
        )

    try:
        root = (
            Path(
                nfo_file.library.path
            )
            .expanduser()
            .resolve(
                strict=True
            )
        )
    except OSError as exc:
        raise PermissionError(
            library_root_problem(exc)
        ) from exc

    destination = (
        root.joinpath(
            *relative.parts
        )
        .resolve(
            strict=False
        )
    )

    try:
        inside_root = (
            destination == root
            or destination.is_relative_to(
                root
            )
        )
    except ValueError:
        inside_root = False

    if not inside_root:
        raise PermissionError(
            "NFO path is outside the configured library root."
        )

    return destination


def write_nfo_file(
    nfo_file: NfoFile,
    raw_xml: str,
):
    if (
        nfo_file.library.management_mode
        == Library.ManagementMode.READ_ONLY
    ):
        raise PermissionError(
            "This library is Read Only. "
            "NFO files cannot be modified."
        )

    raw_xml = str(
        raw_xml
        or ""
    )

    _validate_raw_xml(
        raw_xml
    )

    parsed = _parse_nfo_content(
        raw_xml
    )

    if (
        parsed["status"]
        == NfoFile.ParseStatus.ERROR
    ):
        raise ValueError(
            parsed["error"]
        )

    destination = _destination_for(
        nfo_file
    )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Re-resolve after mkdir so a pre-existing parent symlink cannot move
    # the destination outside the library root between validation steps.
    destination = _destination_for(
        nfo_file
    )

    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{destination.name}.",
            suffix=".libraryforge.tmp",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(
                temporary.name
            )

            temporary.write(
                raw_xml
            )
            temporary.flush()

            try:
                os.fsync(
                    temporary.fileno()
                )
            except OSError:
                pass

        os.replace(
            temporary_path,
            destination,
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

    stat = destination.stat()

    nfo_file.file_name = destination.name
    nfo_file.size_bytes = stat.st_size
    nfo_file.modified_ns = stat.st_mtime_ns
    nfo_file.root_element = parsed[
        "root_element"
    ]
    nfo_file.title = parsed[
        "title"
    ]
    nfo_file.year = parsed[
        "year"
    ]
    nfo_file.raw_xml = raw_xml
    nfo_file.parsed_data = parsed[
        "parsed_data"
    ]
    nfo_file.parse_status = parsed[
        "status"
    ]
    nfo_file.parse_error = ""
    nfo_file.is_present = True
    nfo_file.last_seen_at = (
        timezone.now()
    )

    nfo_file.save()

    return nfo_file
