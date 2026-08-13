import os
import tempfile
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.utils import timezone

from libraries.models import Library
from metadata.models import NfoFile
from metadata.services.nfo import (
    parse_nfo_content as
    _parse_nfo_content,
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
            "The library root is unavailable."
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
