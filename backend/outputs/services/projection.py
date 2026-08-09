import os
import re
import shutil
import xml.etree.ElementTree as ET

from pathlib import (
    Path,
    PurePosixPath,
)

from django.utils import timezone

from metadata.models import MetadataSource

from outputs.models import (
    Projection,
    ProjectionItem,
)


INVALID_FILE_CHARS = re.compile(
    r'[<>:"/\\|?*\x00-\x1f]'
)

TOKEN_PATTERN = re.compile(
    r"\{([a-zA-Z0-9_]+)\}"
)


def _sanitize_segment(value):
    text = str(
        value
        or ""
    ).strip()

    text = INVALID_FILE_CHARS.sub(
        "_",
        text,
    )

    text = text.rstrip(
        ". "
    )

    if text in {
        "",
        ".",
        "..",
    }:
        return "_"

    return text


def _source_data(media_item):
    sources = {
        source.source_type:
            source

        for source in (
            media_item
            .metadata_sources
            .all()
        )

        if (
            source.status
            == MetadataSource
            .Status
            .DETECTED
        )
    }

    def data(source_type):
        source = sources.get(
            source_type
        )

        return (
            source.extracted_data
            if source
            else {}
        )

    ta = data(
        MetadataSource
        .SourceType
        .TUBEARCHIVIST
    )

    ytdlp = data(
        MetadataSource
        .SourceType
        .YT_DLP
    )

    embedded = data(
        MetadataSource
        .SourceType
        .EMBEDDED
    )

    canonical_title = (
        media_item.canonical_metadata
        .get(
            "title"
        )
    )

    title = (
        canonical_title
        or ta.get("title")
        or ytdlp.get("title")
        or embedded.get("title")
        or media_item.title
        or "Untitled"
    )

    canonical_description = (
        media_item.canonical_metadata
        .get(
            "description"
        )
    )

    description = (
        canonical_description
        or media_item.description
        or ta.get("description")
        or ytdlp.get("description")
        or embedded.get("description")
        or ""
    )

    channel = (
        ta.get("channel_name")
        or ta.get("channel")
        or ytdlp.get("channel")
        or ytdlp.get("uploader")
        or "Unknown Channel"
    )

    youtube_id = (
        ta.get("video_id")
        or ta.get("youtube_id")
        or ytdlp.get("id")
        or ""
    )

    upload_date = (
        ta.get("upload_date")
        or ytdlp.get("upload_date")
        or ""
    )

    upload_date = str(
        upload_date
    )

    if (
        len(upload_date) == 8
        and upload_date.isdigit()
    ):
        upload_date = (
            f"{upload_date[0:4]}-"
            f"{upload_date[4:6]}-"
            f"{upload_date[6:8]}"
        )

    return {
        "title":
            title,

        "description":
            description,

        "channel":
            channel,

        "youtube_id":
            youtube_id,

        "date":
            upload_date,

        "media_type":
            media_item.media_type,
    }


def render_relative_base(
    template,
    metadata,
):
    normalized = (
        template
        .replace(
            "\\",
            "/",
        )
        .strip("/")
    )

    raw_parts = [
        part
        for part
        in normalized.split("/")
        if part
    ]

    rendered_parts = []

    for part in raw_parts:
        rendered = TOKEN_PATTERN.sub(
            lambda match:
                str(
                    metadata.get(
                        match.group(1),
                        "",
                    )
                ),
            part,
        )

        rendered_parts.append(
            _sanitize_segment(
                rendered
            )
        )

    if not rendered_parts:
        rendered_parts = [
            _sanitize_segment(
                metadata.get(
                    "title",
                    "Untitled",
                )
            )
        ]

    return Path(
        *rendered_parts
    )


def build_nfo_xml(
    *,
    profile,
    metadata,
):
    root = ET.Element(
        profile.nfo_root_element
        or "movie"
    )

    ET.SubElement(
        root,
        "title",
    ).text = str(
        metadata.get(
            "title",
            "",
        )
    )

    description = (
        metadata.get(
            "description"
        )
        or ""
    )

    if description:
        ET.SubElement(
            root,
            "plot",
        ).text = str(
            description
        )

    date = (
        metadata.get("date")
        or ""
    )

    if date:
        ET.SubElement(
            root,
            "premiered",
        ).text = str(date)

    channel = (
        metadata.get("channel")
        or ""
    )

    if channel:
        ET.SubElement(
            root,
            "studio",
        ).text = str(channel)

    youtube_id = (
        metadata.get(
            "youtube_id"
        )
        or ""
    )

    if youtube_id:
        unique_id = ET.SubElement(
            root,
            "uniqueid",
            {
                "type":
                    "youtube",
            },
        )

        unique_id.text = str(
            youtube_id
        )

    ET.indent(
        root,
        space="  ",
    )

    return ET.tostring(
        root,
        encoding="unicode",
        xml_declaration=False,
    )


def plan_projection_item(
    projection,
    media_file,
):
    media_item = media_file.media_item

    metadata = _source_data(
        media_item
    )

    relative_base = (
        render_relative_base(
            projection.naming_template,
            metadata,
        )
    )

    source_root = Path(
        projection.library.path
    )

    source_path = (
        source_root
        .joinpath(
            *PurePosixPath(
                media_file.relative_path
            ).parts
        )
    )

    destination_root = Path(
        projection.destination_path
    )

    destination_base = (
        destination_root
        / relative_base
    )

    destination_media = (
        destination_base
        .with_suffix(
            source_path.suffix
        )
    )

    destination_nfo = (
        destination_base
        .with_suffix(".nfo")
    )

    return {
        "media_file_id":
            str(media_file.id),

        "title":
            media_item.title,

        "source_path":
            str(source_path),

        "destination_media_path":
            str(destination_media),

        "destination_nfo_path":
            (
                str(destination_nfo)
                if projection.generate_nfo
                else ""
            ),

        "metadata":
            metadata,
    }


def preview_projection(
    projection,
    *,
    limit=50,
):
    media_files = (
        projection.library
        .media_files
        .filter(
            is_present=True
        )
        .select_related(
            "media_item"
        )
        .prefetch_related(
            "media_item__metadata_sources"
        )
        .order_by(
            "relative_path"
        )
    )

    total = media_files.count()

    items = [
        plan_projection_item(
            projection,
            media_file,
        )

        for media_file
        in media_files[:limit]
    ]

    return {
        "total":
            total,

        "preview_count":
            len(items),

        "items":
            items,
    }


def _create_media_target(
    *,
    source_path,
    destination_path,
    link_mode,
):
    destination_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if destination_path.exists():
        return "exists"

    if (
        link_mode
        == Projection.LinkMode.SYMLINK
    ):
        os.symlink(
            source_path,
            destination_path,
        )

    elif (
        link_mode
        == Projection.LinkMode.HARDLINK
    ):
        os.link(
            source_path,
            destination_path,
        )

    else:
        shutil.copy2(
            source_path,
            destination_path,
        )

    return "created"


def run_projection(projection):
    media_files = (
        projection.library
        .media_files
        .filter(
            is_present=True
        )
        .select_related(
            "media_item"
        )
        .prefetch_related(
            "media_item__metadata_sources"
        )
        .order_by(
            "relative_path"
        )
    )

    created = 0
    exists = 0
    errors = []

    for media_file in media_files:
        plan = plan_projection_item(
            projection,
            media_file,
        )

        source_path = Path(
            plan[
                "source_path"
            ]
        )

        destination_media = Path(
            plan[
                "destination_media_path"
            ]
        )

        destination_nfo = (
            Path(
                plan[
                    "destination_nfo_path"
                ]
            )
            if plan[
                "destination_nfo_path"
            ]
            else None
        )

        try:
            result = (
                _create_media_target(
                    source_path=source_path,
                    destination_path=(
                        destination_media
                    ),
                    link_mode=(
                        projection.link_mode
                    ),
                )
            )

            if destination_nfo:
                destination_nfo.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                nfo_xml = build_nfo_xml(
                    profile=(
                        projection
                        .output_profile
                    ),
                    metadata=(
                        plan["metadata"]
                    ),
                )

                destination_nfo.write_text(
                    nfo_xml,
                    encoding="utf-8",
                    newline="\n",
                )

            item_status = (
                ProjectionItem
                .Status
                .CREATED

                if result == "created"

                else ProjectionItem
                .Status
                .EXISTS
            )

            ProjectionItem.objects.update_or_create(
                projection=projection,
                media_file=media_file,
                defaults={
                    "destination_media_path":
                        str(
                            destination_media
                        ),

                    "destination_nfo_path":
                        (
                            str(
                                destination_nfo
                            )
                            if destination_nfo
                            else ""
                        ),

                    "status":
                        item_status,

                    "error":
                        "",
                },
            )

            if result == "created":
                created += 1
            else:
                exists += 1

        except OSError as exc:
            errors.append(
                {
                    "media_file_id":
                        str(
                            media_file.id
                        ),

                    "path":
                        media_file.relative_path,

                    "error":
                        str(exc),
                }
            )

            ProjectionItem.objects.update_or_create(
                projection=projection,
                media_file=media_file,
                defaults={
                    "destination_media_path":
                        str(
                            destination_media
                        ),

                    "destination_nfo_path":
                        (
                            str(
                                destination_nfo
                            )
                            if destination_nfo
                            else ""
                        ),

                    "status":
                        ProjectionItem
                        .Status
                        .ERROR,

                    "error":
                        str(exc),
                },
            )

    projection.last_run_at = (
        timezone.now()
    )

    projection.save(
        update_fields=[
            "last_run_at",
            "updated_at",
        ]
    )

    return {
        "created":
            created,

        "already_exists":
            exists,

        "error_count":
            len(errors),

        "errors":
            errors[:100],
    }
