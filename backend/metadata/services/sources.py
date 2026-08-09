import json

from pathlib import Path

from metadata.models import MetadataSource


def _tag_value(
    tags: dict,
    *names: str,
):
    normalized = {
        str(key).lower():
            value

        for key, value
        in tags.items()
    }

    for name in names:
        value = normalized.get(
            name.lower()
        )

        if value not in (
            None,
            "",
        ):
            return value

    return None


def _save_source(
    media_file,
    source_type,
    status,
    *,
    extracted_data=None,
    raw_data=None,
    error="",
):
    MetadataSource.objects.update_or_create(
        media_file=media_file,
        source_type=source_type,
        defaults={
            "media_item":
                media_file.media_item,

            "status":
                status,

            "extracted_data":
                extracted_data or {},

            "raw_data":
                raw_data or {},

            "error":
                error,
        },
    )


def inspect_metadata_sources(
    *,
    file_path: Path,
    media_file,
    probe_raw: dict | None,
    probe_error: str = "",
):
    _save_source(
        media_file,
        MetadataSource.SourceType.FILENAME,
        MetadataSource.Status.DETECTED,
        extracted_data={
            "title":
                file_path.stem,
        },
        raw_data={
            "file_name":
                file_path.name,

            "relative_path":
                media_file.relative_path,
        },
    )

    if probe_raw:
        _save_source(
            media_file,
            MetadataSource.SourceType.FFPROBE,
            MetadataSource.Status.DETECTED,
            extracted_data={
                "duration_seconds":
                    media_file.duration_seconds,

                "video_codec":
                    media_file.video_codec,

                "width":
                    media_file.width,

                "height":
                    media_file.height,

                "audio_codec":
                    media_file.audio_codec,

                "container_format":
                    media_file.container_format,
            },
        )

    elif probe_error:
        _save_source(
            media_file,
            MetadataSource.SourceType.FFPROBE,
            MetadataSource.Status.ERROR,
            error=probe_error,
        )

    else:
        _save_source(
            media_file,
            MetadataSource.SourceType.FFPROBE,
            MetadataSource.Status.NOT_DETECTED,
        )

    format_tags = {}
    stream_tags = []

    if probe_raw:
        format_tags = (
            probe_raw
            .get(
                "format",
                {},
            )
            .get(
                "tags",
                {},
            )
            or {}
        )

        for stream in probe_raw.get(
            "streams",
            [],
        ):
            tags = (
                stream.get(
                    "tags",
                    {},
                )
                or {}
            )

            if tags:
                stream_tags.append(
                    {
                        "index":
                            stream.get(
                                "index"
                            ),

                        "codec_type":
                            stream.get(
                                "codec_type"
                            ),

                        "tags":
                            tags,
                    }
                )

    if (
        format_tags
        or stream_tags
    ):
        embedded = {
            "title":
                _tag_value(
                    format_tags,
                    "title",
                ),

            "description":
                _tag_value(
                    format_tags,
                    "description",
                    "comment",
                    "synopsis",
                ),

            "date":
                _tag_value(
                    format_tags,
                    "date",
                    "year",
                    "creation_time",
                ),

            "genre":
                _tag_value(
                    format_tags,
                    "genre",
                ),
        }

        embedded = {
            key: value
            for key, value
            in embedded.items()
            if value is not None
        }

        _save_source(
            media_file,
            MetadataSource.SourceType.EMBEDDED,
            MetadataSource.Status.DETECTED,
            extracted_data=embedded,
            raw_data={
                "format_tags":
                    format_tags,

                "stream_tags":
                    stream_tags,
            },
        )

    else:
        _save_source(
            media_file,
            MetadataSource.SourceType.EMBEDDED,
            MetadataSource.Status.NOT_DETECTED,
        )

    ta_value = _tag_value(
        format_tags,
        "ta",
    )

    if ta_value is None:
        _save_source(
            media_file,
            MetadataSource.SourceType.TUBEARCHIVIST,
            MetadataSource.Status.NOT_DETECTED,
        )

    else:
        try:
            if isinstance(
                ta_value,
                str,
            ):
                ta_data = json.loads(
                    ta_value
                )
            else:
                ta_data = ta_value

            extracted = {}

            if isinstance(
                ta_data,
                dict,
            ):
                useful_keys = (
                    "title",
                    "description",
                    "channel_name",
                    "channel",
                    "channel_id",
                    "uploader",
                    "video_id",
                    "youtube_id",
                    "upload_date",
                    "webpage_url",
                    "url",
                    "duration",
                )

                for key in useful_keys:
                    value = ta_data.get(
                        key
                    )

                    if value not in (
                        None,
                        "",
                    ):
                        extracted[key] = (
                            value
                        )

            _save_source(
                media_file,
                MetadataSource.SourceType.TUBEARCHIVIST,
                MetadataSource.Status.DETECTED,
                extracted_data=extracted,
                raw_data={
                    "ta":
                        ta_data,
                },
            )

        except (
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            _save_source(
                media_file,
                MetadataSource.SourceType.TUBEARCHIVIST,
                MetadataSource.Status.ERROR,
                raw_data={
                    "ta":
                        str(
                            ta_value
                        )
                },
                error=str(exc),
            )

    info_json = (
        file_path
        .with_suffix(
            ".info.json"
        )
    )

    if info_json.exists():
        try:
            with info_json.open(
                "r",
                encoding="utf-8",
            ) as handle:
                info_data = json.load(
                    handle
                )

            _save_source(
                media_file,
                MetadataSource.SourceType.YT_DLP,
                MetadataSource.Status.DETECTED,
                extracted_data={
                    key:
                        info_data.get(
                            key
                        )

                    for key in (
                        "id",
                        "title",
                        "description",
                        "uploader",
                        "channel",
                        "channel_id",
                        "upload_date",
                        "webpage_url",
                        "duration",
                    )

                    if info_data.get(
                        key
                    )
                    is not None
                },
                raw_data=info_data,
            )

        except (
            OSError,
            json.JSONDecodeError,
        ) as exc:
            _save_source(
                media_file,
                MetadataSource.SourceType.YT_DLP,
                MetadataSource.Status.ERROR,
                error=str(exc),
            )

    else:
        _save_source(
            media_file,
            MetadataSource.SourceType.YT_DLP,
            MetadataSource.Status.NOT_FOUND,
        )

    nfo_path = (
        file_path
        .with_suffix(
            ".nfo"
        )
    )

    if nfo_path.exists():
        _save_source(
            media_file,
            MetadataSource.SourceType.NFO,
            MetadataSource.Status.DETECTED,
            extracted_data={
                "path":
                    str(
                        nfo_path
                    )
            },
        )

    else:
        _save_source(
            media_file,
            MetadataSource.SourceType.NFO,
            MetadataSource.Status.NOT_FOUND,
        )
