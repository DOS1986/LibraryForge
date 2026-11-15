"""Rating hints for YouTube channels from YouTube's own audience flags.

YouTube doesn't give videos or channels a content rating. It has two
audience flags that the YouTube Data API returns:

* ``status.madeForKids`` on channels and videos (COPPA "made for kids").
* ``contentDetails.contentRating.ytRating == "ytAgeRestricted"`` on videos
  YouTube has age-restricted (18+).

A hint turns those into a US TV rating, from the strongest signal down:

1. Any checked video is age-restricted: ``TV-MA``.
2. The channel is made for kids: ``TV-Y``.
3. At least 90% of the checked videos are made for kids: ``TV-Y``.
4. Otherwise there's no hint. Most general-audience content carries no flag,
   so the person rates it.

``TV-Y`` is a starting point: a made-for-kids channel aimed at older children
may fit ``TV-Y7`` better, which the hint's note says.

Hints are reviewed before use. Applying recomputes them server-side and only
writes a rating that still matches what the person reviewed, with provider
provenance, so a later hint can update it but manual ratings are never
replaced.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from catalog.models import CanonicalFieldState, Channel, MetadataChangeSet, OnlineVideo
from integrations.services import active_links_for_library, provider_for_connection
from libraries.models import Library
from metadata.providers.types import MetadataErrorCategory, MetadataProviderError
from metadata.services.provider_match import MatchRequestError, blocks_provider_update
from metadata.services.ratings import _valid_uuids

PROVIDER = "youtube"
MAX_CHANNELS = 25
# The most recent videos LibraryForge has for a channel, checked per channel.
# 250 videos cost 5 quota units.
MAX_VIDEOS_PER_CHANNEL = 250
KIDS_SHARE = 0.9

HINT_ADULT = "TV-MA"
HINT_KIDS = "TV-Y"

STATUS_HINT = "hint"
STATUS_NO_SIGNAL = "no_signal"
STATUS_NOT_FOUND = "not_found"
STATUS_NOT_YOUTUBE = "not_youtube"

ACTION_SET = "set"
ACTION_CHANGE = "change"
ACTION_UNCHANGED = "unchanged"
ACTION_LOCKED = "locked"

_KIDS_NOTE = "TV-Y is for all children; choose TV-Y7 if the channel is aimed at older kids."


def _connection(library: Library) -> tuple[dict[str, Any] | None, Any]:
    for link in active_links_for_library(library=library, capability="metadata"):
        if link.connection.provider == PROVIDER:
            row = {
                "connection_id": str(link.connection_id),
                "connection_name": link.connection.name,
                "provider": PROVIDER,
                "provider_label": "YouTube",
            }
            return row, link
    return None, None


def _channels(library: Library, ids: list[str], *, for_update: bool = False) -> list[Channel]:
    requested = [str(value).strip() for value in ids if str(value).strip()]
    unique = list(dict.fromkeys(_valid_uuids(requested)))
    if not unique or len(unique) != len(set(requested)):
        raise MatchRequestError("Choose channels with valid IDs.")
    if len(unique) > MAX_CHANNELS:
        raise MatchRequestError(f"Check at most {MAX_CHANNELS} channels at a time.")
    queryset = Channel.objects.filter(library=library, id__in=unique)
    if for_update:
        queryset = queryset.select_for_update()
    channels = list(queryset)
    if len(channels) != len(unique):
        raise MatchRequestError("Some channels aren't in this library.", status=404)
    order = {value: index for index, value in enumerate(unique)}
    return sorted(channels, key=lambda channel: order[str(channel.id)])


def _video_ids(library: Library, channels: list[Channel]) -> dict[str, list[str]]:
    output: dict[str, list[str]] = {}
    for channel in channels:
        if channel.provider != PROVIDER:
            continue
        output[str(channel.id)] = [
            value
            for value in OnlineVideo.objects.filter(library=library, channel=channel, provider=PROVIDER)
            .exclude(source_id="")
            .order_by("-upload_date", "-created_at")
            .values_list("source_id", flat=True)[:MAX_VIDEOS_PER_CHANNEL]
        ]
    return output


def hint_for(channel_signal: dict[str, Any] | None, video_signals: list[dict[str, Any]]) -> dict[str, Any]:
    """The hint for one channel from its YouTube flags (pure; no I/O)."""

    checked = len(video_signals)
    kids = sum(1 for signal in video_signals if signal.get("made_for_kids") is True)
    adult = sum(1 for signal in video_signals if signal.get("age_restricted"))
    stats = {
        "channel_found": channel_signal is not None,
        "channel_made_for_kids": (channel_signal or {}).get("made_for_kids"),
        "videos_checked": checked,
        "videos_made_for_kids": kids,
        "videos_age_restricted": adult,
    }

    if channel_signal is None and not checked:
        return {
            "status": STATUS_NOT_FOUND,
            "rating": "",
            "reason": "YouTube didn't return this channel or any of its videos (they may be private or deleted).",
            "note": "",
            "stats": stats,
        }
    if adult:
        return {
            "status": STATUS_HINT,
            "rating": HINT_ADULT,
            "reason": f"{adult} of {checked} checked videos are age-restricted (18+) on YouTube.",
            "note": "",
            "stats": stats,
        }
    if stats["channel_made_for_kids"] is True:
        return {
            "status": STATUS_HINT,
            "rating": HINT_KIDS,
            "reason": "YouTube lists this channel as made for kids.",
            "note": _KIDS_NOTE,
            "stats": stats,
        }
    if checked and kids / checked >= KIDS_SHARE:
        return {
            "status": STATUS_HINT,
            "rating": HINT_KIDS,
            "reason": f"{kids} of {checked} checked videos are made for kids on YouTube.",
            "note": _KIDS_NOTE,
            "stats": stats,
        }
    detail = f" {kids} of {checked} checked videos are made for kids." if checked else ""
    return {
        "status": STATUS_NO_SIGNAL,
        "rating": "",
        "reason": "YouTube doesn't rate general-audience videos, and this channel isn't marked made for kids."
        + detail
        + " Rate it yourself.",
        "note": "",
        "stats": stats,
    }


def _states(channels: list[Channel]) -> dict[Any, CanonicalFieldState]:
    return {
        state.target_id: state
        for state in CanonicalFieldState.objects.filter(
            target_type=CanonicalFieldState.TargetType.CHANNEL,
            target_id__in=[channel.id for channel in channels],
            field_name="content_rating",
        )
    }


def _action(channel: Channel, hint: dict[str, Any], state: CanonicalFieldState | None) -> str | None:
    if hint["status"] != STATUS_HINT:
        return None
    current = (channel.content_rating or "").strip()
    if current.upper() == hint["rating"]:
        return ACTION_UNCHANGED
    if blocks_provider_update(state):
        return ACTION_LOCKED
    return ACTION_CHANGE if current else ACTION_SET


def _compute(library: Library, channels: list[Channel]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    connection, link = _connection(library)
    if connection is None:
        raise MatchRequestError(
            "No YouTube connection is assigned to this library for metadata. Add your YouTube connection "
            "to the library on its Settings tab.",
            status=409,
        )
    provider = provider_for_connection(link.connection)
    youtube = [channel for channel in channels if channel.provider == PROVIDER and channel.source_id]
    videos = _video_ids(library, youtube)
    try:
        channel_signals = provider.content_signals(
            target_type="channel", source_ids=[channel.source_id for channel in youtube]
        )
        video_signals = provider.content_signals(
            target_type="online_video", source_ids=[value for ids in videos.values() for value in ids]
        )
    except ValueError as exc:
        # validate(): the connection has no API key.
        raise MetadataProviderError(
            MetadataErrorCategory.INVALID_CONFIGURATION, "The YouTube connection has no API key."
        ) from exc

    hints: dict[str, dict[str, Any]] = {}
    for channel in channels:
        if channel not in youtube:
            hints[str(channel.id)] = {
                "status": STATUS_NOT_YOUTUBE,
                "rating": "",
                "reason": "This channel isn't from YouTube.",
                "note": "",
                "stats": {},
            }
            continue
        signals = [video_signals[value] for value in videos.get(str(channel.id), []) if value in video_signals]
        hints[str(channel.id)] = hint_for(channel_signals.get(channel.source_id), signals)
    return connection, hints


def youtube_rating_hints(library: Library, *, ids: list[str]) -> dict[str, Any]:
    channels = _channels(library, ids)
    connection, hints = _compute(library, channels)
    states = _states(channels)
    results = []
    for channel in channels:
        hint = hints[str(channel.id)]
        state = states.get(channel.id)
        results.append(
            {
                "id": str(channel.id),
                "title": channel.title,
                "source_id": channel.source_id,
                "current": channel.content_rating or "",
                "current_source": state.source if state else None,
                "action": _action(channel, hint, state),
                **hint,
            }
        )
    return {"library_id": str(library.id), "connection": connection, "results": results}


def apply_youtube_rating_hints(library: Library, *, user, hints: Any) -> dict[str, Any]:
    """Apply reviewed hints (``{channel_id: rating}``).

    Hints are recomputed; a channel is updated only when its hint still
    equals the reviewed rating and no manual rating protects it.
    """

    if not isinstance(hints, dict) or not hints:
        raise MatchRequestError("Send the reviewed hints as an object of channel ID to rating.")
    reviewed = {str(key).strip(): str(value or "").strip().upper() for key, value in hints.items()}
    channels = _channels(library, list(reviewed))
    connection, fresh = _compute(library, channels)
    retrieved_at = timezone.now()

    results = []
    with transaction.atomic():
        locked_channels = _channels(library, list(reviewed), for_update=True)
        states = _states(locked_channels)
        for channel in locked_channels:
            hint = fresh[str(channel.id)]
            wanted = reviewed[str(channel.id)]
            action = _action(channel, hint, states.get(channel.id))
            if hint["status"] != STATUS_HINT or hint["rating"] != wanted:
                outcome = "changed"
            elif action == ACTION_LOCKED:
                outcome = "locked"
            elif action == ACTION_UNCHANGED:
                outcome = "unchanged"
            else:
                old = channel.content_rating or ""
                channel.content_rating = wanted
                channel.save(update_fields=["content_rating", "updated_at"])
                source_ref = f"{PROVIDER}:channel:{channel.source_id}"[:255]
                CanonicalFieldState.objects.update_or_create(
                    target_type=CanonicalFieldState.TargetType.CHANNEL,
                    target_id=channel.id,
                    field_name="content_rating",
                    defaults={
                        "source": CanonicalFieldState.Source.PROVIDER,
                        "source_ref": source_ref,
                        "value_snapshot": wanted,
                        "locked": True,
                        "updated_by": user,
                    },
                )
                MetadataChangeSet.objects.create(
                    target_type=CanonicalFieldState.TargetType.CHANNEL,
                    target_id=channel.id,
                    source=MetadataChangeSet.Source.PROVIDER,
                    source_ref=source_ref,
                    changes={"content_rating": {"old": old, "new": wanted}},
                    note=f"Rating hint from YouTube's audience flags: {hint['reason']}",
                    changed_by=user,
                    details={
                        "provider": PROVIDER,
                        "provider_label": "YouTube",
                        "connection_id": connection["connection_id"],
                        "connection_name": connection["connection_name"],
                        "target_type": "channel",
                        "source_id": channel.source_id,
                        "hint": True,
                        "hint_stats": hint["stats"],
                        "retrieved_at": retrieved_at.isoformat(),
                    },
                )
                outcome = "applied"
            results.append({"id": str(channel.id), "title": channel.title, "rating": wanted, "result": outcome})

    counts: dict[str, int] = {"applied": 0, "unchanged": 0, "locked": 0, "changed": 0}
    for result in results:
        counts[result["result"]] += 1
    return {"library_id": str(library.id), "counts": counts, "results": results}
