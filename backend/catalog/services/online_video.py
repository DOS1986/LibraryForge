from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from pathlib import PurePosixPath
import re
from typing import Any
from urllib.parse import urlparse

from django.db import transaction
from django.utils import timezone

from catalog.models import (
    CanonicalFieldState,
    Channel,
    MediaVersion,
    OnlineVideo,
    Playlist,
    PlaylistMembership,
    SemanticMatch,
)
from catalog.services.canonical import (
    is_field_locked,
    set_field_provenance,
)
from media.models import MediaFile, MediaItem
from metadata.models import MetadataSource


SOURCE_PRIORITY = (
    MetadataSource.SourceType.TUBEARCHIVIST,
    MetadataSource.SourceType.YT_DLP,
    MetadataSource.SourceType.EMBEDDED,
)

YOUTUBE_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_CHANNEL_ID_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")


def _clean(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _json_safe(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return deepcopy(value)


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _path(data: dict, *parts: str):
    current: Any = data
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return _clean(current)


def _first(data: dict, *paths: tuple[str, ...]):
    for path in paths:
        value = _path(data, *path)
        if value not in (None, "", [], {}):
            return value
    return None


def _parse_date(value) -> date | None:
    value = _clean(value)
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None

    for fmt in (
        "%Y%m%d",
        "%Y-%m-%d",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass

    try:
        return datetime.fromisoformat(
            text.replace("Z", "+00:00")
        ).date()
    except ValueError:
        return None


def _positive_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _normalize_provider(value, *, default="youtube") -> str:
    value = _clean(value)
    if value is None:
        return default

    normalized = str(value).strip().lower()

    youtube_names = {
        "youtube",
        "youtube:tab",
        "youtube:playlist",
        "youtube:search",
        "youtubewebarchive",
        "youtube.com",
        "www.youtube.com",
        "youtu.be",
    }

    if normalized in youtube_names or normalized.startswith("youtube"):
        return "youtube"

    return normalized.replace(" ", "_")


def _handle_from_url(url: str | None) -> str:
    if not url:
        return ""

    try:
        path = urlparse(url).path.strip("/")
    except ValueError:
        return ""

    for part in path.split("/"):
        if part.startswith("@"):
            return part

    return ""


def _tag_value(tags: dict, *names: str):
    normalized = {
        str(key).lower(): value
        for key, value in _dict(tags).items()
    }

    for name in names:
        value = _clean(normalized.get(name.lower()))
        if value not in (None, ""):
            return value

    return None


def _is_youtube_video_id(value: str | None) -> bool:
    return bool(value and YOUTUBE_VIDEO_ID_RE.fullmatch(str(value)))


def _is_youtube_channel_id(value: str | None) -> bool:
    return bool(value and YOUTUBE_CHANNEL_ID_RE.fullmatch(str(value)))


def _normalize_embedded(source: MetadataSource) -> dict:
    extracted = _dict(source.extracted_data)
    raw = _dict(source.raw_data)
    format_tags = _dict(raw.get("format_tags"))

    title = (
        _clean(extracted.get("title"))
        or _tag_value(format_tags, "title")
        or ""
    )
    description = (
        _clean(extracted.get("description"))
        or _tag_value(
            format_tags,
            "description",
            "comment",
            "synopsis",
        )
        or ""
    )
    upload_date = _parse_date(
        _clean(extracted.get("date"))
        or _tag_value(
            format_tags,
            "date",
            "year",
            "creation_time",
        )
    )

    # TubeArchivist embeds the channel display name as Artist. The extra
    # aliases keep this fallback useful for other online-video archives too.
    channel_title = (
        _clean(extracted.get("artist"))
        or _tag_value(
            format_tags,
            "artist",
            "album_artist",
            "albumartist",
            "channel",
            "channel_name",
            "uploader",
        )
        or ""
    )

    genre = (
        _clean(extracted.get("genre"))
        or _tag_value(format_tags, "genre")
        or ""
    )

    return {
        "source_type": MetadataSource.SourceType.EMBEDDED,
        "source_ref": str(source.id),
        "source_version": None,
        "provider": "",
        "video": {
            "id": "",
            "title": title,
            "description": description,
            "url": "",
            "upload_date": upload_date,
            "kind": OnlineVideo.VideoKind.UNKNOWN,
            "tags": [],
            "categories": [genre] if genre else [],
        },
        "channel": {
            "id": "",
            "title": channel_title,
            "url": "",
            "handle": "",
            "description": "",
        },
        "playlists": [],
    }


def _normalize_tubearchivist_path(media_file: MediaFile) -> dict | None:
    # TubeArchivist's documented archive layout is:
    # <channel-id>/<video-id>.mp4
    #
    # Only trust path-derived identity when both IDs validate as YouTube IDs.
    relative = str(media_file.relative_path or "").replace("\\", "/")
    path = PurePosixPath(relative)

    if len(path.parts) < 2:
        return None

    channel_id = path.parts[-2]
    video_id = PurePosixPath(path.parts[-1]).stem

    if not _is_youtube_channel_id(channel_id):
        return None

    if not _is_youtube_video_id(video_id):
        return None

    return {
        "source_type": CanonicalFieldState.Source.TUBEARCHIVIST_PATH,
        "source_ref": f"tubearchivist-path:{relative}",
        "source_version": None,
        "provider": "youtube",
        "identity_basis": "tubearchivist_path",
        "video": {
            "id": video_id,
            "title": "",
            "description": "",
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "upload_date": None,
            "kind": OnlineVideo.VideoKind.UNKNOWN,
            "tags": [],
            "categories": [],
        },
        "channel": {
            "id": channel_id,
            "title": "",
            "url": f"https://www.youtube.com/channel/{channel_id}",
            "handle": "",
            "description": "",
        },
        "playlists": [],
    }


def _video_kind(value, *, url: str = "", live_status: str = "") -> str:
    normalized = str(value or "").strip().lower()
    live = str(live_status or "").strip().lower()
    lowered_url = (url or "").lower()

    if normalized in {"short", "shorts"} or "/shorts/" in lowered_url:
        return OnlineVideo.VideoKind.SHORT

    if normalized in {
        "stream",
        "streams",
        "live",
        "livestream",
    }:
        return OnlineVideo.VideoKind.STREAM

    if live in {
        "is_live",
        "was_live",
        "post_live",
    } or "/live/" in lowered_url:
        return OnlineVideo.VideoKind.STREAM

    if normalized in {"video", "videos"}:
        return OnlineVideo.VideoKind.VIDEO

    if url:
        return OnlineVideo.VideoKind.VIDEO

    return OnlineVideo.VideoKind.UNKNOWN


def _playlist_entries(value) -> list[dict]:
    if value in (None, "", [], {}):
        return []

    if isinstance(value, list):
        return [entry for entry in value if isinstance(entry, dict)]

    if isinstance(value, dict):
        # A single playlist object.
        if any(
            key in value
            for key in (
                "playlist_id",
                "id",
                "playlist_name",
                "playlist_title",
                "title",
            )
        ):
            return [value]

        # Some archived structures use an id -> playlist mapping.
        entries = []
        for key, entry in value.items():
            if isinstance(entry, dict):
                copied = dict(entry)
                copied.setdefault("playlist_id", key)
                entries.append(copied)
        return entries

    return []


def _normalize_tubearchivist(source: MetadataSource) -> dict:
    raw = _dict(source.raw_data)
    ta = raw.get("ta", raw)
    ta = _dict(ta)

    video = _dict(
        _first(
            ta,
            ("video",),
            ("video_data",),
            ("data",),
        )
    )

    # Prefer the explicit video object, then fall back to the TA root.
    merged_video = dict(ta)
    merged_video.update(video)

    channel_value = _first(
        merged_video,
        ("channel",),
        ("channel_data",),
    )
    channel = _dict(channel_value)

    video_id = _first(
        merged_video,
        ("youtube_id",),
        ("video_id",),
        ("id",),
    )

    title = _first(
        merged_video,
        ("title",),
        ("fulltitle",),
    )

    description = _first(
        merged_video,
        ("description",),
        ("video_description",),
    )

    webpage_url = _first(
        merged_video,
        ("webpage_url",),
        ("media_url",),
        ("url",),
    )

    channel_id = _first(
        channel,
        ("channel_id",),
        ("youtube_id",),
        ("id",),
    ) or _first(
        merged_video,
        ("channel_id",),
    )

    if isinstance(channel_value, str):
        channel_title = channel_value
    else:
        channel_title = _first(
            channel,
            ("channel_name",),
            ("name",),
            ("title",),
        ) or _first(
            merged_video,
            ("channel_name",),
            ("uploader",),
        )

    channel_url = _first(
        channel,
        ("channel_url",),
        ("url",),
    ) or _first(
        merged_video,
        ("channel_url",),
    )

    channel_description = _first(
        channel,
        ("channel_description",),
        ("description",),
    )

    upload_date = _parse_date(
        _first(
            merged_video,
            ("upload_date",),
            ("published",),
            ("published_at",),
            ("date_published",),
        )
    )

    raw_playlists = _first(
        ta,
        ("playlists",),
        ("playlist",),
        ("playlist_data",),
        ("video", "playlists"),
        ("video", "playlist"),
        ("data", "playlists"),
        ("data", "playlist"),
    )

    playlists = []
    for entry in _playlist_entries(raw_playlists):
        playlist_id = _first(
            entry,
            ("playlist_id",),
            ("id",),
        )
        if not playlist_id:
            continue

        playlists.append(
            {
                "id": str(playlist_id),
                "title": _first(
                    entry,
                    ("playlist_name",),
                    ("playlist_title",),
                    ("title",),
                    ("name",),
                ) or str(playlist_id),
                "description": _first(
                    entry,
                    ("playlist_description",),
                    ("description",),
                ) or "",
                "url": _first(
                    entry,
                    ("playlist_url",),
                    ("webpage_url",),
                    ("url",),
                ) or "",
                "position": _positive_int(
                    _first(
                        entry,
                        ("playlist_position",),
                        ("playlist_index",),
                        ("position",),
                        ("index",),
                    )
                ),
                "kind": (
                    Playlist.PlaylistKind.CUSTOM
                    if bool(
                        _first(
                            entry,
                            ("is_custom",),
                            ("custom",),
                        )
                    )
                    else Playlist.PlaylistKind.REMOTE
                ),
            }
        )

    provider = "youtube"
    video_id = str(video_id) if video_id is not None else ""
    channel_id = str(channel_id) if channel_id is not None else ""

    return {
        "source_type": MetadataSource.SourceType.TUBEARCHIVIST,
        "source_ref": str(source.id),
        "source_version": _first(
            ta,
            ("version",),
            ("ta_version",),
            ("metadata_version",),
        ),
        "provider": provider,
        "video": {
            "id": video_id,
            "title": title or "",
            "description": description or "",
            "url": webpage_url or "",
            "upload_date": upload_date,
            "kind": _video_kind(
                _first(
                    merged_video,
                    ("vid_type",),
                    ("video_type",),
                    ("type",),
                ),
                url=webpage_url or "",
            ),
            "tags": _list(
                _first(
                    merged_video,
                    ("tags",),
                    ("video_tags",),
                )
            ),
            "categories": _list(
                _first(
                    merged_video,
                    ("categories",),
                    ("category",),
                )
            ),
        },
        "channel": {
            "id": channel_id,
            "title": channel_title or "",
            "url": channel_url or "",
            "handle": _handle_from_url(channel_url or ""),
            "description": channel_description or "",
        },
        "playlists": playlists,
    }


def _normalize_ytdlp(source: MetadataSource) -> dict:
    data = _dict(source.raw_data)

    provider = _normalize_provider(
        _first(
            data,
            ("extractor_key",),
            ("extractor",),
            ("webpage_url_domain",),
        ),
        default="youtube",
    )

    webpage_url = _first(
        data,
        ("webpage_url",),
        ("original_url",),
        ("url",),
    ) or ""

    channel_url = _first(
        data,
        ("channel_url",),
        ("uploader_url",),
    ) or ""

    channel_id = _first(
        data,
        ("channel_id",),
        ("uploader_id",),
    )

    playlist_id = _first(
        data,
        ("playlist_id",),
    )

    playlists = []
    if playlist_id:
        playlists.append(
            {
                "id": str(playlist_id),
                "title": _first(
                    data,
                    ("playlist_title",),
                    ("playlist",),
                ) or str(playlist_id),
                "description": _first(
                    data,
                    ("playlist_description",),
                ) or "",
                "url": _first(
                    data,
                    ("playlist_webpage_url",),
                ) or "",
                "position": _positive_int(
                    _first(
                        data,
                        ("playlist_index",),
                        ("playlist_autonumber",),
                    )
                ),
                "kind": Playlist.PlaylistKind.REMOTE,
            }
        )

    video_id = _first(data, ("id",), ("display_id",))

    return {
        "source_type": MetadataSource.SourceType.YT_DLP,
        "source_ref": str(source.id),
        "source_version": _first(data, ("_version",), ("version",)),
        "provider": provider,
        "video": {
            "id": str(video_id) if video_id is not None else "",
            "title": _first(data, ("title",), ("fulltitle",)) or "",
            "description": _first(data, ("description",)) or "",
            "url": webpage_url,
            "upload_date": _parse_date(
                _first(
                    data,
                    ("upload_date",),
                    ("release_date",),
                    ("modified_date",),
                )
            ),
            "kind": _video_kind(
                _first(data, ("video_type",), ("type",)),
                url=webpage_url,
                live_status=_first(data, ("live_status",)) or "",
            ),
            "tags": _list(_first(data, ("tags",))),
            "categories": _list(_first(data, ("categories",))),
        },
        "channel": {
            "id": str(channel_id) if channel_id is not None else "",
            "title": _first(
                data,
                ("channel",),
                ("uploader",),
            ) or "",
            "url": channel_url,
            "handle": _first(data, ("channel_handle",))
            or _handle_from_url(channel_url),
            "description": "",
        },
        "playlists": playlists,
    }


def _detected_source(media_file: MediaFile, source_type: str):
    for source in media_file.metadata_sources.all():
        if (
            source.source_type == source_type
            and source.status == MetadataSource.Status.DETECTED
        ):
            return source
    return None


def _merge_candidates(candidates: list[dict]) -> dict:
    merged = {
        "provider": "",
        "video": {},
        "channel": {},
        "playlists": [],
        "provenance": {},
        "source_versions": {},
    }

    playlist_map: dict[tuple[str, str], dict] = {}

    for candidate in candidates:
        if not candidate:
            continue

        source_type = candidate["source_type"]
        source_ref = candidate["source_ref"]

        if candidate.get("source_version") not in (None, ""):
            merged["source_versions"][source_type] = candidate["source_version"]

        if not merged["provider"] and candidate.get("provider"):
            merged["provider"] = candidate["provider"]
            merged["provenance"]["provider"] = (source_type, source_ref)

        for section in ("video", "channel"):
            target = merged[section]
            for field_name, value in candidate.get(section, {}).items():
                if value in (None, "", [], {}):
                    continue
                if target.get(field_name) in (None, "", [], {}):
                    target[field_name] = deepcopy(value)
                    merged["provenance"][f"{section}.{field_name}"] = (
                        source_type,
                        source_ref,
                    )

        provider = candidate.get("provider") or merged["provider"] or "unknown"
        for playlist in candidate.get("playlists", []):
            playlist_id = str(playlist.get("id") or "")
            if not playlist_id:
                continue

            key = (provider, playlist_id)
            if key not in playlist_map:
                playlist_map[key] = deepcopy(playlist)
                playlist_map[key]["provider"] = provider
                playlist_map[key]["source_type"] = source_type
                playlist_map[key]["source_ref"] = source_ref
            else:
                current = playlist_map[key]
                for field_name, value in playlist.items():
                    if current.get(field_name) in (None, "", [], {}) and value not in (
                        None,
                        "",
                        [],
                        {},
                    ):
                        current[field_name] = deepcopy(value)

    merged["playlists"] = list(playlist_map.values())
    return merged


def _source_value(provenance: dict, field: str):
    source_type, source_ref = provenance.get(
        field,
        (CanonicalFieldState.Source.SYSTEM, ""),
    )
    return source_type, source_ref


def _apply_field(
    *,
    target,
    target_type: str,
    field_name: str,
    value,
    source_type: str,
    source_ref: str,
):
    if value in (None, ""):
        return False

    if getattr(target, "locked", False):
        return False

    if is_field_locked(
        target_type=target_type,
        target_id=target.id,
        field_name=field_name,
    ):
        return False

    changed = getattr(target, field_name) != value
    if changed:
        setattr(target, field_name, value)
        target.save(update_fields=[field_name, "updated_at"])

    set_field_provenance(
        target_type=target_type,
        target_id=target.id,
        field_name=field_name,
        source=source_type,
        source_ref=source_ref,
        value=value,
    )

    return changed


def _apply_media_item_field(
    *,
    media_item: MediaItem,
    field_name: str,
    value,
    source_type: str,
    source_ref: str,
):
    if value in (None, ""):
        return False

    if is_field_locked(
        target_type=CanonicalFieldState.TargetType.MEDIA_ITEM,
        target_id=media_item.id,
        field_name=field_name,
    ):
        return False

    changed = getattr(media_item, field_name) != value
    if changed:
        setattr(media_item, field_name, value)
        media_item.save(update_fields=[field_name, "updated_at"])

    set_field_provenance(
        target_type=CanonicalFieldState.TargetType.MEDIA_ITEM,
        target_id=media_item.id,
        field_name=field_name,
        source=source_type,
        source_ref=source_ref,
        value=value,
    )

    return changed


def channel_semantic_key(provider: str, source_id: str) -> str:
    return f"channel:{provider}:{source_id}"


def online_video_semantic_key(provider: str, source_id: str) -> str:
    return f"online-video:{provider}:{source_id}"


def playlist_semantic_key(provider: str, source_id: str) -> str:
    return f"playlist:{provider}:{source_id}"


def _ensure_channel(*, library, merged: dict) -> Channel | None:
    channel_data = merged.get("channel", {})
    source_id = str(channel_data.get("id") or "")
    if not source_id:
        return None

    provider = merged.get("provider") or "unknown"
    semantic_key = channel_semantic_key(provider, source_id)

    channel, _created = Channel.objects.get_or_create(
        library=library,
        provider=provider,
        source_id=source_id,
        defaults={
            "semantic_key": semantic_key,
            "title": channel_data.get("title") or source_id,
            "sort_title": channel_data.get("title") or source_id,
            "source_url": channel_data.get("url") or "",
            "handle": channel_data.get("handle") or "",
            "description": channel_data.get("description") or "",
            "external_ids": {provider: source_id},
            "canonical_metadata": {
                "semantic": {
                    "kind": "channel",
                    "provider": provider,
                    "source_id": source_id,
                }
            },
        },
    )

    update_fields = []
    if channel.semantic_key != semantic_key:
        channel.semantic_key = semantic_key
        update_fields.append("semantic_key")

    external_ids = dict(channel.external_ids or {})
    if external_ids.get(provider) != source_id:
        external_ids[provider] = source_id
        channel.external_ids = external_ids
        update_fields.append("external_ids")

    metadata = dict(channel.canonical_metadata or {})
    semantic = dict(metadata.get("semantic") or {})
    desired_semantic = {
        "kind": "channel",
        "provider": provider,
        "source_id": source_id,
    }
    if semantic != desired_semantic:
        metadata["semantic"] = desired_semantic
        channel.canonical_metadata = metadata
        update_fields.append("canonical_metadata")

    if update_fields:
        channel.save(update_fields=[*update_fields, "updated_at"])

    provenance = merged.get("provenance", {})
    for model_field, normalized_field in (
        ("title", "channel.title"),
        ("source_url", "channel.url"),
        ("handle", "channel.handle"),
        ("description", "channel.description"),
    ):
        value = channel_data.get(normalized_field.split(".", 1)[1])
        source_type, source_ref = _source_value(provenance, normalized_field)
        _apply_field(
            target=channel,
            target_type=CanonicalFieldState.TargetType.CHANNEL,
            field_name=model_field,
            value=value,
            source_type=source_type,
            source_ref=source_ref,
        )

    if not channel.sort_title and channel.title:
        channel.sort_title = channel.title
        channel.save(update_fields=["sort_title", "updated_at"])

    return channel


def _ensure_version(*, media_item: MediaItem, media_file: MediaFile):
    version, _created = MediaVersion.objects.get_or_create(
        media_file=media_file,
        defaults={
            "media_item": media_item,
            "name": "Default",
            "is_primary": False,
        },
    )

    changed = False
    if version.media_item_id != media_item.id:
        version.media_item = media_item
        changed = True

    has_primary = MediaVersion.objects.filter(
        media_item=media_item,
        is_primary=True,
    ).exclude(pk=version.pk).exists()

    if not has_primary and not version.is_primary:
        version.is_primary = True
        changed = True

    if changed:
        version.save()

    return version


def _mark_match(
    *,
    media_file: MediaFile,
    status: str,
    source: str = "",
    confidence: float = 0,
    candidate_data: dict | None = None,
):
    match, _created = SemanticMatch.objects.update_or_create(
        media_file=media_file,
        defaults={
            "status": status,
            "source": source,
            "confidence": confidence,
            "candidate_data": _json_safe(candidate_data or {}),
            "last_resolved_at": timezone.now(),
        },
    )
    return match


def _source_candidates(media_file: MediaFile) -> tuple[list[dict], dict]:
    candidates = []
    identity_candidates = {}

    ta_source = _detected_source(
        media_file,
        MetadataSource.SourceType.TUBEARCHIVIST,
    )
    if ta_source:
        normalized = _normalize_tubearchivist(ta_source)
        candidates.append(normalized)
        identity_candidates[
            MetadataSource.SourceType.TUBEARCHIVIST
        ] = normalized

    yt_source = _detected_source(
        media_file,
        MetadataSource.SourceType.YT_DLP,
    )
    if yt_source:
        normalized = _normalize_ytdlp(yt_source)
        candidates.append(normalized)
        identity_candidates[
            MetadataSource.SourceType.YT_DLP
        ] = normalized

    embedded_source = _detected_source(
        media_file,
        MetadataSource.SourceType.EMBEDDED,
    )
    if embedded_source:
        candidates.append(
            _normalize_embedded(embedded_source)
        )

    path_candidate = _normalize_tubearchivist_path(media_file)
    if path_candidate:
        candidates.append(path_candidate)
        identity_candidates["tubearchivist_path"] = path_candidate

    return candidates, identity_candidates


def _identity_conflict(identity_candidates: dict) -> bool:
    identities = set()

    for candidate in identity_candidates.values():
        provider = candidate.get("provider") or ""
        source_id = candidate.get("video", {}).get("id") or ""

        if not provider or not source_id:
            continue

        identities.add((str(provider), str(source_id)))

    return len(identities) > 1


def resolve_online_video_file(*, library, media_file: MediaFile) -> str:
    existing_match = getattr(media_file, "semantic_match", None)
    if existing_match and existing_match.locked:
        return "locked"

    candidates, identity_candidates = _source_candidates(media_file)

    if _identity_conflict(identity_candidates):
        _mark_match(
            media_file=media_file,
            status=SemanticMatch.Status.CONFLICT,
            confidence=0,
            candidate_data={
                "kind": "online_video",
                "reason": "source_identity_disagreement",
                "sources": identity_candidates,
            },
        )
        return "conflict"

    merged = _merge_candidates(candidates)
    provider = merged.get("provider") or ""
    video_data = merged.get("video", {})
    source_id = str(video_data.get("id") or "")

    if not provider or not source_id:
        if media_file.media_item.media_type != MediaItem.MediaType.ONLINE_VIDEO:
            media_file.media_item.media_type = MediaItem.MediaType.ONLINE_VIDEO
            media_file.media_item.save(update_fields=["media_type", "updated_at"])

        _mark_match(
            media_file=media_file,
            status=SemanticMatch.Status.UNRESOLVED,
            confidence=0.25 if candidates else 0,
            candidate_data={
                "kind": "online_video",
                "reason": "stable_source_identity_missing",
                "candidate": merged,
            },
        )
        return "unresolved"

    semantic_key = online_video_semantic_key(provider, source_id)
    media_item = media_file.media_item

    if (
        media_item.semantic_locked
        and media_item.semantic_key
        and media_item.semantic_key != semantic_key
    ):
        _mark_match(
            media_file=media_file,
            status=SemanticMatch.Status.CONFLICT,
            confidence=0,
            candidate_data={
                "kind": "online_video",
                "reason": "locked_identity_disagreement",
                "current_semantic_key": media_item.semantic_key,
                "candidate_semantic_key": semantic_key,
                "candidate": merged,
            },
        )
        return "conflict"

    duplicate = OnlineVideo.objects.filter(
        library=library,
        provider=provider,
        source_id=source_id,
    ).exclude(media_item=media_item).first()

    if duplicate:
        _mark_match(
            media_file=media_file,
            status=SemanticMatch.Status.CONFLICT,
            confidence=0,
            candidate_data={
                "kind": "online_video",
                "reason": "duplicate_source_identity",
                "existing_media_item_id": str(duplicate.media_item_id),
                "candidate": merged,
            },
        )
        return "conflict"

    existing_video = OnlineVideo.objects.filter(media_item=media_item).first()
    if existing_video and (
        existing_video.provider != provider
        or existing_video.source_id != source_id
    ):
        _mark_match(
            media_file=media_file,
            status=SemanticMatch.Status.CONFLICT,
            confidence=0,
            candidate_data={
                "kind": "online_video",
                "reason": "existing_identity_disagreement",
                "existing": {
                    "provider": existing_video.provider,
                    "source_id": existing_video.source_id,
                },
                "candidate": merged,
            },
        )
        return "conflict"

    with transaction.atomic():
        channel = _ensure_channel(library=library, merged=merged)

        media_item.media_type = MediaItem.MediaType.ONLINE_VIDEO
        media_item.semantic_key = semantic_key

        metadata = dict(media_item.canonical_metadata or {})
        metadata["semantic"] = {
            "kind": "online_video",
            "provider": provider,
            "source_id": source_id,
        }
        metadata["online_video"] = {
            "provider": provider,
            "source_id": source_id,
            "source_versions": merged.get("source_versions", {}),
        }
        media_item.canonical_metadata = metadata
        media_item.save(
            update_fields=[
                "media_type",
                "semantic_key",
                "canonical_metadata",
                "updated_at",
            ]
        )

        provenance = merged.get("provenance", {})
        for field_name, normalized_field in (
            ("title", "video.title"),
            ("description", "video.description"),
            ("release_date", "video.upload_date"),
        ):
            value = video_data.get(normalized_field.split(".", 1)[1])
            source_type, source_ref = _source_value(provenance, normalized_field)
            _apply_media_item_field(
                media_item=media_item,
                field_name=field_name,
                value=value,
                source_type=source_type,
                source_ref=source_ref,
            )

        online_video, _created = OnlineVideo.objects.get_or_create(
            media_item=media_item,
            defaults={
                "library": library,
                "provider": provider,
                "source_id": source_id,
                "channel": channel,
                "source_url": video_data.get("url") or "",
                "upload_date": video_data.get("upload_date"),
                "video_kind": video_data.get("kind")
                or OnlineVideo.VideoKind.UNKNOWN,
                "tags": video_data.get("tags") or [],
                "categories": video_data.get("categories") or [],
                "external_ids": {provider: source_id},
                "canonical_metadata": {
                    "semantic": {
                        "kind": "online_video",
                        "provider": provider,
                        "source_id": source_id,
                    },
                    "source_versions": merged.get("source_versions", {}),
                },
            },
        )

        if online_video.channel_id != (channel.id if channel else None):
            online_video.channel = channel
            online_video.save(update_fields=["channel", "updated_at"])

        external_ids = dict(online_video.external_ids or {})
        external_ids[provider] = source_id
        online_video.external_ids = external_ids

        video_metadata = dict(online_video.canonical_metadata or {})
        video_metadata["semantic"] = {
            "kind": "online_video",
            "provider": provider,
            "source_id": source_id,
        }
        video_metadata["source_versions"] = merged.get("source_versions", {})
        online_video.canonical_metadata = video_metadata
        online_video.save(
            update_fields=[
                "external_ids",
                "canonical_metadata",
                "updated_at",
            ]
        )

        for model_field, normalized_field in (
            ("source_url", "video.url"),
            ("upload_date", "video.upload_date"),
            ("video_kind", "video.kind"),
            ("tags", "video.tags"),
            ("categories", "video.categories"),
        ):
            value = video_data.get(normalized_field.split(".", 1)[1])
            source_type, source_ref = _source_value(provenance, normalized_field)
            _apply_field(
                target=online_video,
                target_type=CanonicalFieldState.TargetType.ONLINE_VIDEO,
                field_name=model_field,
                value=value,
                source_type=source_type,
                source_ref=source_ref,
            )

        for playlist_data in merged.get("playlists", []):
            playlist_id = str(playlist_data.get("id") or "")
            playlist_provider = playlist_data.get("provider") or provider
            if not playlist_id:
                continue

            playlist, _created = Playlist.objects.get_or_create(
                library=library,
                provider=playlist_provider,
                source_id=playlist_id,
                defaults={
                    "semantic_key": playlist_semantic_key(
                        playlist_provider,
                        playlist_id,
                    ),
                    "channel": channel,
                    "title": playlist_data.get("title") or playlist_id,
                    "description": playlist_data.get("description") or "",
                    "source_url": playlist_data.get("url") or "",
                    "playlist_kind": playlist_data.get("kind")
                    or Playlist.PlaylistKind.UNKNOWN,
                    "external_ids": {playlist_provider: playlist_id},
                    "canonical_metadata": {
                        "semantic": {
                            "kind": "playlist",
                            "provider": playlist_provider,
                            "source_id": playlist_id,
                        }
                    },
                },
            )

            playlist_updates = []
            expected_key = playlist_semantic_key(playlist_provider, playlist_id)
            if playlist.semantic_key != expected_key:
                playlist.semantic_key = expected_key
                playlist_updates.append("semantic_key")

            if channel and playlist.channel_id != channel.id:
                playlist.channel = channel
                playlist_updates.append("channel")

            if playlist_updates:
                playlist.save(update_fields=[*playlist_updates, "updated_at"])

            playlist_source = (
                playlist_data.get(
                    "source_type"
                )
                or CanonicalFieldState.Source.SYSTEM
            )
            playlist_ref = playlist_data.get("source_ref") or ""
            for field_name, key in (
                ("title", "title"),
                ("description", "description"),
                ("source_url", "url"),
                ("playlist_kind", "kind"),
            ):
                _apply_field(
                    target=playlist,
                    target_type=CanonicalFieldState.TargetType.PLAYLIST,
                    field_name=field_name,
                    value=playlist_data.get(key),
                    source_type=playlist_source,
                    source_ref=playlist_ref,
                )

            PlaylistMembership.objects.update_or_create(
                playlist=playlist,
                online_video=online_video,
                defaults={
                    "position": playlist_data.get("position"),
                    "metadata": {
                        "source_type": playlist_source,
                        "source_ref": playlist_ref,
                    },
                },
            )

        _ensure_version(media_item=media_item, media_file=media_file)

        identity_source, identity_ref = _source_value(
            provenance,
            "video.id",
        )
        if identity_source == CanonicalFieldState.Source.SYSTEM:
            identity_source = (
                candidates[0]["source_type"] if candidates else ""
            )

        identity_basis = identity_source
        confidence = 1.0

        if (
            identity_source
            == CanonicalFieldState.Source.TUBEARCHIVIST_PATH
            and str(identity_ref).startswith("tubearchivist-path:")
        ):
            identity_basis = "tubearchivist_path"
            confidence = 0.98

        _mark_match(
            media_file=media_file,
            status=SemanticMatch.Status.MATCHED,
            source=identity_source,
            confidence=confidence,
            candidate_data={
                "kind": "online_video",
                "semantic_key": semantic_key,
                "identity_basis": identity_basis,
                "identity_source_ref": identity_ref,
                "candidate": merged,
            },
        )

    return "matched"


def resolve_online_video_library(*, library):
    if library.content_type != "online_video":
        return {
            "matched": 0,
            "unresolved": 0,
            "conflict": 0,
            "locked": 0,
            "error_count": 0,
            "errors": [],
        }

    result = {
        "matched": 0,
        "unresolved": 0,
        "conflict": 0,
        "locked": 0,
        "error_count": 0,
        "errors": [],
    }

    media_files = (
        MediaFile.objects
        .filter(
            library=library,
            is_present=True,
        )
        .select_related(
            "media_item",
        )
        .prefetch_related(
            "metadata_sources",
        )
        .order_by(
            "relative_path",
        )
    )

    for media_file in media_files:
        try:
            status = resolve_online_video_file(
                library=library,
                media_file=media_file,
            )
            if status in result:
                result[status] += 1
        except Exception as exc:
            result["error_count"] += 1
            if len(result["errors"]) < 100:
                result["errors"].append(
                    {
                        "path": media_file.relative_path,
                        "error": str(exc),
                    }
                )

    return result
