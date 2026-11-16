"""Edit online videos and channels by hand.

Online-video metadata normally comes from the file's embedded tags and
TubeArchivist. Hand edits here are recorded like every other manual edit:
each changed field is locked with a manual source and gets a history entry,
so later scans never overwrite it. The Jellyfin "Channels as TV shows" folder
writes these values into its NFOs on its next sync.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.db import transaction

from catalog.models import CanonicalFieldState, Channel, OnlineVideo
from catalog.services.canonical import (
    _record_manual_changes,
    _set_attr_changes,
    serialize_field_states,
    serialize_history,
)
from metadata.services.provider_match import MatchRequestError

MAX_TITLE = 1024
MAX_DESCRIPTION = 50_000
MAX_TAGS = 100
MAX_RATING = 64


def _text(values: dict[str, Any], name: str, limit: int, *, allow_empty: bool = True) -> str:
    value = values[name]
    if not isinstance(value, str):
        raise MatchRequestError(f"{name.replace('_', ' ').capitalize()} must be text.")
    value = value.strip()
    if len(value) > limit:
        raise MatchRequestError(f"{name.replace('_', ' ').capitalize()} is at most {limit} characters.")
    if not value and not allow_empty:
        raise MatchRequestError(f"{name.replace('_', ' ').capitalize()} can't be empty.")
    return value


def _rating(values: dict[str, Any]) -> str:
    from metadata.services.ratings import RECOGNIZED_RATINGS

    value = " ".join(_text(values, "content_rating", MAX_RATING).split())
    return value.upper() if value.upper() in RECOGNIZED_RATINGS else value


def _date(value: Any) -> datetime.date | None:
    if value in (None, ""):
        return None
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError as exc:
        raise MatchRequestError("Dates must be YYYY-MM-DD.") from exc


def _tags(value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise MatchRequestError("Tags must be a list of text.")
    tags = list(dict.fromkeys(" ".join(item.split()) for item in value if item.strip()))
    if len(tags) > MAX_TAGS or any(len(tag) > 200 for tag in tags):
        raise MatchRequestError(f"Use at most {MAX_TAGS} tags of up to 200 characters.")
    return tags


# ---------------------------------------------------------------------------
# Online videos
# ---------------------------------------------------------------------------


def online_video_detail(video: OnlineVideo) -> dict[str, Any]:
    item = video.media_item
    files = list(item.files.filter(is_present=True).values_list("relative_path", flat=True)) if hasattr(item, "files") else []
    return {
        "kind": "online_video",
        "id": str(video.id),
        "library_id": str(video.library_id),
        "provider": video.provider,
        "source_id": video.source_id,
        "source_url": video.source_url,
        "title": item.title,
        "description": item.description,
        "content_rating": item.content_rating,
        "upload_date": video.upload_date.isoformat() if video.upload_date else None,
        "video_kind": video.video_kind,
        "video_kind_label": video.get_video_kind_display(),
        "tags": list(video.tags or []),
        "channel": (
            {"id": str(video.channel.id), "title": video.channel.title, "content_rating": video.channel.content_rating}
            if video.channel
            else None
        ),
        "files": files,
        "field_states": [
            *serialize_field_states(target_type=CanonicalFieldState.TargetType.MEDIA_ITEM, target_id=item.id),
            *serialize_field_states(target_type=CanonicalFieldState.TargetType.ONLINE_VIDEO, target_id=video.id),
        ],
        "history": sorted(
            [
                *serialize_history(target_type=CanonicalFieldState.TargetType.MEDIA_ITEM, target_id=item.id),
                *serialize_history(target_type=CanonicalFieldState.TargetType.ONLINE_VIDEO, target_id=video.id),
            ],
            key=lambda change: str(change.get("created_at") or ""),
            reverse=True,
        ),
    }


@transaction.atomic
def update_online_video(*, video: OnlineVideo, values: dict[str, Any], user, note: str = "") -> dict[str, Any]:
    item = video.media_item
    item_values: dict[str, Any] = {}
    video_values: dict[str, Any] = {}
    if "title" in values:
        item_values["title"] = _text(values, "title", MAX_TITLE, allow_empty=False)
    if "description" in values:
        item_values["description"] = _text(values, "description", MAX_DESCRIPTION)
    if "content_rating" in values:
        item_values["content_rating"] = _rating(values)
    if "upload_date" in values:
        upload = _date(values["upload_date"])
        video_values["upload_date"] = upload
        # The catalog's release date follows the upload date.
        item_values["release_date"] = upload
    if "tags" in values:
        video_values["tags"] = _tags(values["tags"])
    unknown = sorted(set(values) - {"title", "description", "content_rating", "upload_date", "tags"})
    if unknown:
        raise MatchRequestError(f"These fields can't be edited: {', '.join(unknown)}.")

    item_changes = _set_attr_changes(obj=item, values=item_values)
    video_changes = _set_attr_changes(obj=video, values=video_values)
    if item_changes:
        item.save()
        _record_manual_changes(
            target_type=CanonicalFieldState.TargetType.MEDIA_ITEM, target_id=item.id, changes=item_changes, user=user, note=note
        )
    if video_changes:
        video.save()
        _record_manual_changes(
            target_type=CanonicalFieldState.TargetType.ONLINE_VIDEO,
            target_id=video.id,
            changes=video_changes,
            user=user,
            note=note,
        )
    return online_video_detail(video)


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------


def channel_detail(channel: Channel) -> dict[str, Any]:
    return {
        "kind": "channel",
        "id": str(channel.id),
        "library_id": str(channel.library_id),
        "provider": channel.provider,
        "source_id": channel.source_id,
        "source_url": channel.source_url,
        "handle": channel.handle,
        "title": channel.title,
        "sort_title": channel.sort_title,
        "description": channel.description,
        "content_rating": channel.content_rating,
        "video_count": channel.videos.count(),
        "field_states": serialize_field_states(target_type=CanonicalFieldState.TargetType.CHANNEL, target_id=channel.id),
        "history": serialize_history(target_type=CanonicalFieldState.TargetType.CHANNEL, target_id=channel.id),
    }


@transaction.atomic
def update_channel(*, channel: Channel, values: dict[str, Any], user, note: str = "") -> dict[str, Any]:
    clean: dict[str, Any] = {}
    if "title" in values:
        clean["title"] = _text(values, "title", MAX_TITLE, allow_empty=False)
    if "sort_title" in values:
        clean["sort_title"] = _text(values, "sort_title", MAX_TITLE)
    if "description" in values:
        clean["description"] = _text(values, "description", MAX_DESCRIPTION)
    if "content_rating" in values:
        clean["content_rating"] = _rating(values)
    unknown = sorted(set(values) - {"title", "sort_title", "description", "content_rating"})
    if unknown:
        raise MatchRequestError(f"These fields can't be edited: {', '.join(unknown)}.")

    changes = _set_attr_changes(obj=channel, values=clean)
    if changes:
        channel.save()
        _record_manual_changes(
            target_type=CanonicalFieldState.TargetType.CHANNEL, target_id=channel.id, changes=changes, user=user, note=note
        )
    return channel_detail(channel)
