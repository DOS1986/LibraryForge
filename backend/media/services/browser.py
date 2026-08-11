from pathlib import PurePosixPath

from media.models import MediaFile
from catalog.models import ArtworkFile, Channel
from metadata.models import NfoFile


VALID_CONTENT_MODES = {
    "media",
    "files",
    "nfo",
}

VALID_ORDERING_FIELDS = {
    "name",
    "media_count",
    "nfo_count",
    "file_count",
    "duration_seconds",
    "size_bytes",
}


def normalize_folder_path(
    value: str,
):
    raw = (
        value
        or ""
    ).replace(
        "\\",
        "/",
    ).strip("/")

    if not raw:
        return ""

    path = PurePosixPath(
        raw
    )

    if (
        path.is_absolute()
        or ".." in path.parts
    ):
        raise ValueError(
            "Invalid folder path."
        )

    return path.as_posix()


def normalize_content_mode(
    value: str,
):
    mode = (
        value
        or "media"
    ).strip().lower()

    if mode not in VALID_CONTENT_MODES:
        raise ValueError(
            "Content mode must be "
            "media, files, or nfo."
        )

    return mode


def normalize_ordering(
    value: str,
):
    raw = (
        value
        or "name"
    ).strip()

    descending = (
        raw.startswith("-")
    )

    field = (
        raw[1:]
        if descending
        else raw
    )

    if (
        field
        not in VALID_ORDERING_FIELDS
    ):
        field = "name"
        descending = False

    return (
        field,
        descending,
    )


def build_breadcrumbs(
    current_path: str,
):
    breadcrumbs = [
        {
            "name":
                "Library",

            "path":
                "",
        }
    ]

    if not current_path:
        return breadcrumbs

    parts = PurePosixPath(
        current_path
    ).parts

    accumulated = []

    for part in parts:
        accumulated.append(
            part
        )

        breadcrumbs.append(
            {
                "name":
                    part,

                "path":
                    PurePosixPath(
                        *accumulated
                    ).as_posix(),
            }
        )

    return breadcrumbs


def _relative_remainder(
    relative_path: str,
    current_path: str,
):
    normalized = PurePosixPath(
        relative_path
    ).as_posix()

    if not current_path:
        return normalized

    prefix = (
        current_path
        + "/"
    )

    if not normalized.startswith(
        prefix
    ):
        return None

    return normalized[
        len(prefix):
    ]


def _folder_entry(
    *,
    folder_name: str,
    folder_path: str,
    folder_title: str | None = None,
):
    return {
        "entry_type":
            "folder",

        "name":
            folder_name,

        "title":
            folder_title
            or folder_name,

        "relative_path":
            folder_path,

        "media_count":
            0,

        "nfo_count":
            0,

        "artwork_count":
            0,

        "file_count":
            0,

        "duration_seconds":
            0.0,

        "size_bytes":
            0,
    }


def _sort_value(
    entry,
    field: str,
):
    if field == "name":
        return (
            entry
            .get(
                "title",
                "",
            )
            or entry
            .get(
                "name",
                "",
            )
        ).casefold()

    value = entry.get(
        field
    )

    if value is None:
        return 0

    return value


def _sort_entries(
    entries,
    *,
    ordering_field: str,
    descending: bool,
):
    folders = [
        entry
        for entry
        in entries
        if (
            entry[
                "entry_type"
            ]
            == "folder"
        )
    ]

    files = [
        entry
        for entry
        in entries
        if (
            entry[
                "entry_type"
            ]
            != "folder"
        )
    ]

    folders.sort(
        key=lambda item:
            _sort_value(
                item,
                ordering_field,
            ),
        reverse=descending,
    )

    files.sort(
        key=lambda item:
            _sort_value(
                item,
                ordering_field,
            ),
        reverse=descending,
    )

    return (
        folders
        + files
    )


def build_library_browser_entries(
    *,
    library,
    current_path: str,
    content_mode: str,
    ordering: str,
):
    include_media = (
        content_mode
        in {
            "media",
            "files",
        }
    )

    include_nfo = (
        content_mode
        in {
            "nfo",
            "files",
        }
    )

    prefix = (
        f"{current_path}/"
        if current_path
        else ""
    )

    folders = {}
    direct_entries = []

    channel_titles = {}
    if (
        not current_path
        and getattr(
            library,
            "content_type",
            "",
        ) == "online_video"
    ):
        channel_titles = dict(
            Channel.objects
            .filter(
                library=library,
            )
            .exclude(
                source_id="",
            )
            .values_list(
                "source_id",
                "title",
            )
        )

    if include_media:
        media_queryset = (
            MediaFile.objects
            .filter(
                library=library,
                is_present=True,
            )
            .select_related(
                "media_item"
            )
        )

        if prefix:
            media_queryset = (
                media_queryset
                .filter(
                    relative_path__startswith=(
                        prefix
                    )
                )
            )

        for media_file in media_queryset:
            remainder = (
                _relative_remainder(
                    media_file.relative_path,
                    current_path,
                )
            )

            if not remainder:
                continue

            parts = PurePosixPath(
                remainder
            ).parts

            if len(parts) > 1:
                folder_name = (
                    parts[0]
                )

                folder_path = (
                    PurePosixPath(
                        current_path,
                        folder_name,
                    )
                    .as_posix()
                    .lstrip("/")
                )

                folder = folders.setdefault(
                    folder_name.casefold(),
                    _folder_entry(
                        folder_name=folder_name,
                        folder_path=folder_path,
                        folder_title=(
                            channel_titles
                            .get(folder_name)
                        ),
                    ),
                )

                folder[
                    "media_count"
                ] += 1

                folder[
                    "file_count"
                ] += 1

                folder[
                    "size_bytes"
                ] += (
                    media_file
                    .size_bytes
                    or 0
                )

                folder[
                    "duration_seconds"
                ] += (
                    media_file
                    .duration_seconds
                    or 0.0
                )

                continue

            direct_entries.append(
                {
                    "entry_type":
                        "media",

                    "id":
                        str(
                            media_file.id
                        ),

                    "media_item":
                        str(
                            media_file
                            .media_item_id
                        ),

                    "name":
                        media_file
                        .file_name,

                    "title":
                        media_file
                        .media_item
                        .title,

                    "relative_path":
                        media_file
                        .relative_path,

                    "media_count":
                        1,

                    "nfo_count":
                        0,

                    "artwork_count":
                        0,

                    "file_count":
                        1,

                    "size_bytes":
                        media_file
                        .size_bytes,

                    "duration_seconds":
                        media_file
                        .duration_seconds,

                    "video_codec":
                        media_file
                        .video_codec,

                    "width":
                        media_file
                        .width,

                    "height":
                        media_file
                        .height,

                    "metadata_status":
                        media_file
                        .probe_status,
                }
            )

    if include_nfo:
        nfo_queryset = (
            NfoFile.objects
            .filter(
                library=library,
                is_present=True,
            )
            .select_related(
                "media_item"
            )
        )

        if prefix:
            nfo_queryset = (
                nfo_queryset
                .filter(
                    relative_path__startswith=(
                        prefix
                    )
                )
            )

        for nfo_file in nfo_queryset:
            remainder = (
                _relative_remainder(
                    nfo_file.relative_path,
                    current_path,
                )
            )

            if not remainder:
                continue

            parts = PurePosixPath(
                remainder
            ).parts

            if len(parts) > 1:
                folder_name = (
                    parts[0]
                )

                folder_path = (
                    PurePosixPath(
                        current_path,
                        folder_name,
                    )
                    .as_posix()
                    .lstrip("/")
                )

                folder = folders.setdefault(
                    folder_name.casefold(),
                    _folder_entry(
                        folder_name=folder_name,
                        folder_path=folder_path,
                        folder_title=(
                            channel_titles
                            .get(folder_name)
                        ),
                    ),
                )

                folder[
                    "nfo_count"
                ] += 1

                folder[
                    "file_count"
                ] += 1

                folder[
                    "size_bytes"
                ] += (
                    nfo_file
                    .size_bytes
                    or 0
                )

                continue

            direct_entries.append(
                {
                    "entry_type":
                        "nfo",

                    "id":
                        str(
                            nfo_file.id
                        ),

                    "media_item":
                        (
                            str(
                                nfo_file
                                .media_item_id
                            )
                            if (
                                nfo_file
                                .media_item_id
                            )
                            else None
                        ),

                    "name":
                        nfo_file
                        .file_name,

                    "title":
                        (
                            nfo_file.title
                            or (
                                nfo_file
                                .media_item
                                .title
                                if (
                                    nfo_file
                                    .media_item
                                )
                                else ""
                            )
                            or nfo_file
                            .file_name
                        ),

                    "relative_path":
                        nfo_file
                        .relative_path,

                    "media_count":
                        0,

                    "nfo_count":
                        1,

                    "artwork_count":
                        0,

                    "file_count":
                        1,

                    "size_bytes":
                        nfo_file
                        .size_bytes,

                    "duration_seconds":
                        None,

                    "video_codec":
                        "",

                    "width":
                        None,

                    "height":
                        None,

                    "metadata_status":
                        nfo_file
                        .parse_status,
                }
            )

    if content_mode == "files":
        artwork_queryset = (
            ArtworkFile.objects
            .exclude(relative_path__startswith="@embedded/")
            .filter(
                library=library,
                is_present=True,
            )
        )

        if prefix:
            artwork_queryset = (
                artwork_queryset
                .filter(
                    relative_path__startswith=(
                        prefix
                    )
                )
            )

        for artwork in artwork_queryset:
            remainder = (
                _relative_remainder(
                    artwork.relative_path,
                    current_path,
                )
            )

            if not remainder:
                continue

            parts = PurePosixPath(
                remainder
            ).parts

            if len(parts) > 1:
                folder_name = parts[0]

                folder_path = (
                    PurePosixPath(
                        current_path,
                        folder_name,
                    )
                    .as_posix()
                    .lstrip("/")
                )

                folder = folders.setdefault(
                    folder_name.casefold(),
                    _folder_entry(
                        folder_name=folder_name,
                        folder_path=folder_path,
                        folder_title=(
                            channel_titles
                            .get(folder_name)
                        ),
                    ),
                )

                folder[
                    "artwork_count"
                ] += 1

                folder[
                    "file_count"
                ] += 1

                folder[
                    "size_bytes"
                ] += (
                    artwork.size_bytes
                    or 0
                )

                continue

            direct_entries.append(
                {
                    "entry_type":
                        "artwork",
                    "id":
                        str(artwork.id),
                    "media_item":
                        None,
                    "name":
                        artwork.file_name,
                    "title":
                        artwork.file_name,
                    "relative_path":
                        artwork.relative_path,
                    "media_count":
                        0,
                    "nfo_count":
                        0,
                    "artwork_count":
                        1,
                    "file_count":
                        1,
                    "size_bytes":
                        artwork.size_bytes,
                    "duration_seconds":
                        None,
                    "video_codec":
                        "",
                    "width":
                        None,
                    "height":
                        None,
                    "metadata_status":
                        artwork.artwork_type,
                }
            )

    entries = (
        list(
            folders.values()
        )
        + direct_entries
    )

    (
        ordering_field,
        descending,
    ) = normalize_ordering(
        ordering
    )

    return _sort_entries(
        entries,
        ordering_field=(
            ordering_field
        ),
        descending=descending,
    )
