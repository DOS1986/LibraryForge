import os
import xml.etree.ElementTree as ET

from pathlib import (
    Path,
    PurePosixPath,
)

from django.utils import timezone

from metadata.models import NfoFile


MAX_NFO_BYTES = 10 * 1024 * 1024


def _clean_tag(tag: str):
    if "}" in tag:
        return tag.split("}", 1)[1]

    return tag


def _element_to_data(element):
    children = list(element)

    if not children:
        return (
            element.text
            or ""
        ).strip()

    result = {}

    for child in children:
        key = _clean_tag(child.tag)
        value = _element_to_data(child)

        if key in result:
            existing = result[key]

            if not isinstance(existing, list):
                result[key] = [existing]

            result[key].append(value)

        else:
            result[key] = value

    return result


def _first_text(root, *names):
    wanted = {
        name.lower()
        for name in names
    }

    for element in root.iter():
        if (
            _clean_tag(element.tag).lower()
            in wanted
        ):
            value = (
                element.text
                or ""
            ).strip()

            if value:
                return value

    return ""


def parse_nfo_content(raw_xml: str):
    text = (
        raw_xml
        or ""
    ).strip()

    if not text:
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
                "NFO file is empty.",
        }

    # Kodi parsing NFOs may contain a plain URL instead
    # of a full XML document.
    if not text.startswith("<"):
        return {
            "status":
                NfoFile.ParseStatus.OK,

            "root_element":
                "text",

            "title":
                "",

            "year":
                None,

            "parsed_data":
                {
                    "text": text,
                },

            "error":
                "",
        }

    try:
        root = ET.fromstring(text)

    except ET.ParseError as exc:
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

    title = _first_text(
        root,
        "title",
    )

    year_text = _first_text(
        root,
        "year",
    )

    year = None

    if year_text:
        try:
            year = int(
                year_text[:4]
            )

        except (
            TypeError,
            ValueError,
        ):
            year = None

    return {
        "status":
            NfoFile.ParseStatus.OK,

        "root_element":
            _clean_tag(
                root.tag
            ),

        "title":
            title,

        "year":
            year,

        "parsed_data":
            {
                _clean_tag(root.tag):
                    _element_to_data(root)
            },

        "error":
            "",
    }


def filesystem_path(
    root: Path,
    relative_path: str,
):
    posix_path = PurePosixPath(
        relative_path
    )

    return root.joinpath(
        *posix_path.parts
    )


def build_media_stem_index(
    media_files,
):
    index = {}
    folder_index = {}

    for media_file in media_files:
        relative = PurePosixPath(
            media_file.relative_path
        )

        stem_key = str(
            relative.with_suffix("")
        ).casefold()

        index[stem_key] = (
            media_file
        )

        folder_key = str(
            relative.parent
        ).casefold()

        folder_index.setdefault(
            folder_key,
            [],
        ).append(
            media_file
        )

    return (
        index,
        folder_index,
    )


def match_nfo_to_media(
    relative_path: str,
    media_stem_index,
    folder_index,
):
    relative = PurePosixPath(
        relative_path
    )

    direct_key = str(
        relative.with_suffix("")
    ).casefold()

    direct = (
        media_stem_index
        .get(
            direct_key
        )
    )

    if direct:
        return direct

    if (
        relative.name.casefold()
        == "movie.nfo"
    ):
        folder_key = str(
            relative.parent
        ).casefold()

        folder_media = (
            folder_index
            .get(
                folder_key,
                [],
            )
        )

        if len(folder_media) == 1:
            return folder_media[0]

    return None


def sync_nfo_file(
    *,
    library,
    root: Path,
    nfo_path: Path,
    media_stem_index,
    folder_index,
    scan_time,
):
    relative_path = (
        nfo_path
        .relative_to(root)
        .as_posix()
    )

    stat = nfo_path.stat()

    media_file = (
        match_nfo_to_media(
            relative_path,
            media_stem_index,
            folder_index,
        )
    )

    media_item = (
        media_file.media_item
        if media_file
        else None
    )

    existing = (
        NfoFile.objects
        .filter(
            library=library,
            relative_path=relative_path,
        )
        .first()
    )

    unchanged = (
        existing is not None

        and existing.size_bytes
        == stat.st_size

        and existing.modified_ns
        == stat.st_mtime_ns
    )

    if unchanged:
        existing.is_present = True
        existing.last_seen_at = scan_time

        if media_file:
            existing.media_file = media_file
            existing.media_item = media_item

        existing.save(
            update_fields=[
                "is_present",
                "last_seen_at",
                "media_file",
                "media_item",
                "updated_at",
            ]
        )

        return (
            existing,
            False,
            False,
        )

    if stat.st_size > MAX_NFO_BYTES:
        raw_xml = ""

        parsed = {
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
                (
                    "NFO file exceeds the "
                    "10 MB inspection limit."
                ),
        }

    else:
        try:
            raw_xml = (
                nfo_path.read_text(
                    encoding="utf-8-sig"
                )
            )

            parsed = parse_nfo_content(
                raw_xml
            )

        except UnicodeDecodeError as exc:
            raw_xml = ""

            parsed = {
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
                    (
                        "NFO is not valid "
                        f"UTF-8: {exc}"
                    ),
            }

    nfo_file, created = (
        NfoFile.objects
        .update_or_create(
            library=library,
            relative_path=relative_path,
            defaults={
                "media_item":
                    media_item,

                "media_file":
                    media_file,

                "file_name":
                    nfo_path.name,

                "size_bytes":
                    stat.st_size,

                "modified_ns":
                    stat.st_mtime_ns,

                "root_element":
                    parsed[
                        "root_element"
                    ],

                "title":
                    parsed[
                        "title"
                    ],

                "year":
                    parsed[
                        "year"
                    ],

                "raw_xml":
                    raw_xml,

                "parsed_data":
                    parsed[
                        "parsed_data"
                    ],

                "parse_status":
                    parsed[
                        "status"
                    ],

                "parse_error":
                    parsed[
                        "error"
                    ],

                "is_present":
                    True,

                "last_seen_at":
                    scan_time,
            },
        )
    )

    return (
        nfo_file,
        created,
        not created,
    )


def write_nfo_file(
    nfo_file: NfoFile,
    raw_xml: str,
):
    from libraries.models import Library

    if (
        nfo_file.library.management_mode
        == Library.ManagementMode.READ_ONLY
    ):
        raise PermissionError(
            "This library is Read Only. "
            "NFO files cannot be modified."
        )

    parsed = parse_nfo_content(
        raw_xml
    )

    if (
        parsed["status"]
        == NfoFile.ParseStatus.ERROR
    ):
        raise ValueError(
            parsed["error"]
        )

    library_root = Path(
        nfo_file.library.path
    )

    destination = filesystem_path(
        library_root,
        nfo_file.relative_path,
    )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = (
        destination.parent
        / (
            f".{destination.name}."
            "libraryforge.tmp"
        )
    )

    try:
        temporary.write_text(
            raw_xml,
            encoding="utf-8",
            newline="\n",
        )

        os.replace(
            temporary,
            destination,
        )

    finally:
        try:
            temporary.unlink(
                missing_ok=True
            )
        except OSError:
            pass

    stat = destination.stat()

    nfo_file.file_name = destination.name
    nfo_file.size_bytes = stat.st_size
    nfo_file.modified_ns = stat.st_mtime_ns

    nfo_file.root_element = (
        parsed[
            "root_element"
        ]
    )

    nfo_file.title = (
        parsed[
            "title"
        ]
    )

    nfo_file.year = (
        parsed[
            "year"
        ]
    )

    nfo_file.raw_xml = raw_xml

    nfo_file.parsed_data = (
        parsed[
            "parsed_data"
        ]
    )

    nfo_file.parse_status = (
        parsed[
            "status"
        ]
    )

    nfo_file.parse_error = ""
    nfo_file.is_present = True
    nfo_file.last_seen_at = timezone.now()

    nfo_file.save()

    return nfo_file
