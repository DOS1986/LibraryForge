"""Channels as TV shows: a Jellyfin-ready folder built from an online-video library.

TubeArchivist stores videos as ``<channel-id>/<video-id>.mp4`` and keeps the
metadata in its own database. This builds a separate folder in the layout
Jellyfin expects, without touching TubeArchivist's files:

    <destination>/
      <Channel>/
        tvshow.nfo                      title, description, rating, YouTube ID
        poster.jpg, fanart.jpg          channel artwork from the library's integration
        Season 2024/
          S2024E051201 - <Title> [<video id>].mp4         hardlink to the original
          S2024E051201 - <Title> [<video id>].nfo         episode NFO
          S2024E051201 - <Title> [<video id>]-thumb.jpg   embedded thumbnail

Seasons are upload years. Episode numbers are the upload month and day plus
a same-day counter (``051201`` is 12 May, first video that day). A number,
once given, is kept, so later downloads never renumber existing episodes.
Show names aren't repeated in file names, which keeps paths well under the
Windows 260-character limit.

Videos are hardlinked: the same data under a second name, so no extra disk
space is used and TubeArchivist keeps working. Hardlinks need the destination
on the same volume as the library.

Safety:

* Every file LibraryForge writes is recorded in ``ProjectionFile``. A sync only
  replaces or deletes files in that manifest; anything else in the destination
  is reported as a conflict and left alone.
* A written file is only replaced or deleted if it still has the content (or,
  for video links, the size) LibraryForge recorded.
* Paths are confined to the destination, which must be separate from the
  library. Source files are confined to the library root and only read.
* The plan is computed from the database alone; files are checked when each
  change is applied. A sync runs in batches, one at a time per destination.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

from catalog.models import ArtworkFile, Channel
from catalog.services.artwork import embedded_artwork_locator
from integrations.security import fetch_remote_artwork
from integrations.services import active_links_for_library, provider_for_connection
from media.models import MediaFile
from metadata.services.provider_match import MatchRequestError
from outputs.models import Projection, ProjectionFile
from outputs.services.fileops import (  # noqa: F401 - shared helpers
    _CROSS_DEVICE_WINERRORS,
    _INVALID,
    _RESERVED,
    _XML_INVALID,
    ACTION_ARTWORK,
    ACTION_CREATE,
    ACTION_DELETE,
    ACTION_RELINK,
    ACTION_REPLACE,
    ACTION_UPDATE,
    ACTIONS,
    MAX_THUMB_BYTES,
    RESULTS,
    Action,
    Desired,
    _apply,
    _clean,
    _Conflict,
    _create,
    _CrossDevice,
    _destination_root,
    _file_sha,
    _is_ours,
    _link,
    _matches_source,
    _place,
    _prune,
    _record,
    _remove_ours,
    _same_file,
    _sha,
    _source,
    _target,
    _thumbnail,
    _write_bytes,
    _xml,
    destination_error,
    safe_segment,
)

Kind = ProjectionFile.Kind

MAX_SHOW_NAME = 60
MAX_TITLE = 80
DEFAULT_BATCH = 25
MAX_BATCH = 200
SAMPLE_LIMIT = 200
MAX_ARTWORK_BYTES = 15 * 1024 * 1024


_EXTENSION = re.compile(r"^[a-z0-9]{1,8}$")
_IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


# ---------------------------------------------------------------------------
# Names and NFO documents
# ---------------------------------------------------------------------------


def show_nfo(channel: Channel, *, premiered: str = "") -> bytes:
    return _xml(
        "tvshow",
        [
            ("title", channel.title, {}),
            ("sorttitle", channel.sort_title, {}),
            ("plot", channel.description, {}),
            ("mpaa", channel.content_rating, {}),
            ("premiered", premiered, {}),
            ("studio", "YouTube", {}),
            ("uniqueid", channel.source_id, {"type": "youtube", "default": "true"}),
        ],
    )


def episode_nfo(*, media_file: MediaFile, video, channel: Channel, season: int, episode: int) -> bytes:
    item = media_file.media_item
    aired = video.upload_date.isoformat() if video.upload_date else ""
    runtime = round(media_file.duration_seconds / 60) if media_file.duration_seconds else None
    rating = (item.content_rating or "").strip() or channel.content_rating
    kind_tag = {"short": "Short", "stream": "Live stream"}.get(video.video_kind, "")
    return _xml(
        "episodedetails",
        [
            ("title", item.title or video.source_id, {}),
            ("showtitle", channel.title, {}),
            ("season", season, {}),
            ("episode", episode, {}),
            ("aired", aired, {}),
            ("premiered", aired, {}),
            ("plot", item.description, {}),
            ("runtime", runtime if runtime else "", {}),
            ("mpaa", rating, {}),
            ("studio", channel.title, {}),
            ("tag", kind_tag, {}),
            ("uniqueid", video.source_id, {"type": "youtube", "default": "true"}),
        ],
    )


# ---------------------------------------------------------------------------
# Planning (database only)
# ---------------------------------------------------------------------------


def _videos(library) -> list[tuple[Any, MediaFile]]:
    """One present file per online video that has a channel."""

    chosen: dict[Any, tuple[Any, MediaFile]] = {}
    files = (
        MediaFile.objects.filter(
            library=library, is_present=True, media_item__online_video__channel__isnull=False
        )
        .select_related("media_item", "media_item__online_video", "media_item__online_video__channel")
        .order_by("relative_path")
    )
    for media_file in files:
        video = media_file.media_item.online_video
        chosen.setdefault(video.id, (video, media_file))
    return list(chosen.values())


def _show_names(channels: list[Channel]) -> dict[Any, str]:
    names: dict[Any, str] = {}
    used: set[str] = set()
    for channel in sorted(channels, key=lambda value: (value.title.casefold(), value.source_id)):
        name = safe_segment(channel.title, MAX_SHOW_NAME)
        counter = 1
        while name.casefold() in used:
            # Two channels with one name: tell them apart by channel ID.
            suffix = f" [{safe_segment(channel.source_id, 40)}]" + (f" {counter}" if counter > 1 else "")
            name = safe_segment(channel.title, MAX_SHOW_NAME - len(suffix)) + suffix
            counter += 1
        used.add(name.casefold())
        names[channel.id] = name
    return names


def _thumb_streams(library) -> dict[str, int]:
    streams: dict[str, int] = {}
    for relative_path in (
        ArtworkFile.objects.filter(
            library=library,
            target_type=ArtworkFile.TargetType.MEDIA_ITEM,
            is_present=True,
            relative_path__startswith="@embedded/",
        )
        .order_by("-is_selected", "relative_path")
        .values_list("relative_path", flat=True)
    ):
        locator = embedded_artwork_locator(relative_path)
        if locator:
            streams.setdefault(str(locator[0]), locator[1])
    return streams


def _keeps_number(assigned: tuple[int | None, int | None] | None, year: int, prefix: str) -> bool:
    if not assigned or assigned[0] != year or assigned[1] is None:
        return False
    text = str(assigned[1])
    return text.startswith(prefix) and len(text) - len(prefix) in (2, 3)


def _episode_numbers(videos, assigned) -> dict[Any, tuple[int, int, str]]:
    """(season, episode, token) per media file: kept if still valid, else next free."""

    output: dict[Any, tuple[int, int, str]] = {}
    used: dict[tuple, set[int]] = defaultdict(set)
    pending: dict[tuple, list] = defaultdict(list)
    for video, media_file in videos:
        day = video.upload_date or video.created_at.date()
        key = (video.channel_id, day)
        prefix = str(int(f"{day.month:02d}{day.day:02d}"))
        keep = assigned.get(media_file.id)
        if _keeps_number(keep, day.year, prefix) and keep[1] not in used[key]:
            used[key].add(keep[1])
            output[media_file.id] = (day.year, keep[1], f"{day.month:02d}{day.day:02d}{str(keep[1])[len(prefix):]}")
        else:
            pending[key].append((video, media_file))
    for key, items in pending.items():
        day = key[1]
        prefix = f"{day.month:02d}{day.day:02d}"
        counter = 1
        for _video, media_file in sorted(items, key=lambda pair: pair[0].source_id):
            while int(f"{prefix}{counter:02d}") in used[key]:
                counter += 1
            number = int(f"{prefix}{counter:02d}")
            used[key].add(number)
            output[media_file.id] = (day.year, number, f"{prefix}{counter:02d}")
    return output


def _desired(projection, manifest) -> tuple[list[Desired], dict[Any, str], list[Channel]]:
    library = projection.library
    videos = _videos(library)
    channels = {video.channel_id: video.channel for video, _file in videos}
    names = _show_names(list(channels.values()))
    assigned = {
        row.media_file_id: (row.season_number, row.episode_number)
        for row in manifest.values()
        if row.kind == Kind.VIDEO and row.media_file_id
    }
    numbers = _episode_numbers(videos, assigned)
    thumbs = _thumb_streams(library)

    desired: list[Desired] = []
    first_upload: dict[Any, str] = {}
    for video, media_file in videos:
        channel = channels[video.channel_id]
        season, episode, token = numbers[media_file.id]
        title = safe_segment(media_file.media_item.title or video.source_id, MAX_TITLE)
        base = f"{names[channel.id]}/Season {season}/S{season}E{token} - {title} [{safe_segment(video.source_id, 32)}]"
        extension = (media_file.extension or "").lower().lstrip(".")
        if not _EXTENSION.fullmatch(extension):
            extension = "mp4"
        desired.append(
            Desired(f"{base}.{extension}", Kind.VIDEO, channel, media_file, season=season, episode=episode)
        )
        desired.append(
            Desired(
                f"{base}.nfo",
                Kind.EPISODE_NFO,
                channel,
                media_file,
                content=episode_nfo(
                    media_file=media_file, video=video, channel=channel, season=season, episode=episode
                ),
            )
        )
        stream = thumbs.get(str(media_file.id))
        if stream is not None:
            desired.append(Desired(f"{base}-thumb.jpg", Kind.THUMB, channel, media_file, stream_index=stream))
        if video.upload_date:
            day = video.upload_date.isoformat()
            first_upload[channel.id] = min(first_upload.get(channel.id, day), day)

    for channel in channels.values():
        desired.append(
            Desired(
                f"{names[channel.id]}/tvshow.nfo",
                Kind.SHOW_NFO,
                channel,
                content=show_nfo(channel, premiered=first_upload.get(channel.id, "")),
            )
        )
    return desired, names, sorted(channels.values(), key=lambda value: value.title.casefold())


def _artwork_links(library) -> list:
    return active_links_for_library(library=library, capability="artwork")


def _plan(projection) -> dict[str, Any]:
    manifest = {row.relative_path: row for row in ProjectionFile.objects.filter(projection=projection)}
    folded = {path.casefold(): path for path in manifest}
    desired, names, channels = _desired(projection, manifest)
    has_artwork = bool(_artwork_links(projection.library))

    actions: list[Action] = []
    wanted: set[str] = set()
    for item in desired:
        # Keep the recorded spelling when only letter case changed, so a
        # case-insensitive share never sees a create-then-delete of one file.
        item.path = folded.get(item.path.casefold(), item.path)
        wanted.add(item.path)
        row = manifest.get(item.path)
        if row is None:
            actions.append(Action(ACTION_CREATE, item.kind, item.path, item.channel, item))
        elif row.kind != item.kind or (item.media_file and row.media_file_id != item.media_file.id):
            actions.append(Action(ACTION_REPLACE, item.kind, item.path, item.channel, item, row))
        elif item.kind == Kind.VIDEO and row.size_bytes != item.media_file.size_bytes:
            # TubeArchivist replaced the file (for example a re-download).
            actions.append(Action(ACTION_RELINK, item.kind, item.path, item.channel, item, row))
        elif item.content is not None and row.content_sha256 != _sha(item.content):
            actions.append(Action(ACTION_UPDATE, item.kind, item.path, item.channel, item, row))

    show_folders = {names[channel.id]: channel for channel in channels}
    art_rows: dict[str, list[ProjectionFile]] = defaultdict(list)
    for path, row in manifest.items():
        if row.kind in (Kind.POSTER, Kind.FANART):
            folder = str(PurePosixPath(path).parent)
            if folder in show_folders:
                wanted.add(path)
                art_rows[folder].append(row)
    if has_artwork:
        for folder, channel in show_folders.items():
            if not any(row.kind == Kind.POSTER for row in art_rows[folder]):
                actions.append(Action(ACTION_ARTWORK, "artwork", f"{folder}/poster", channel))

    channel_by_id = {channel.id: channel for channel in channels}
    for path, row in manifest.items():
        if path not in wanted:
            actions.append(Action(ACTION_DELETE, row.kind, path, channel_by_id.get(row.channel_id), row=row))

    actions.sort(key=lambda action: action.sort_key)
    return {"actions": actions, "desired": desired, "names": names, "channels": channels, "has_artwork": has_artwork}


def _filtered(actions: list[Action], channel_id: str | None) -> list[Action]:
    if not channel_id:
        return actions
    return [action for action in actions if action.channel and str(action.channel.id) == str(channel_id)]


# ---------------------------------------------------------------------------
# Applying one planned action (the engine journals and sequences them)
# ---------------------------------------------------------------------------


def _require_layout(projection) -> None:
    if projection.layout != Projection.Layout.YOUTUBE_SHOWS:
        raise MatchRequestError("This projection doesn't use the Channels as TV shows layout.")


def _channel_artwork(library, channel: Channel) -> dict[str, tuple[bytes, str]]:
    found: dict[str, tuple[bytes, str]] = {}
    for link in _artwork_links(library):
        try:
            provider = provider_for_connection(link.connection)
            item = provider.lookup_one(target_type="channel", source_id=channel.source_id) or {}
        except Exception:  # noqa: BLE001, S112 - artwork is optional; try the next integration
            continue
        raw = item.get("raw") or {}
        urls = {
            Kind.POSTER: _find_url(raw, ("channel_thumb_url",)) or str(item.get("artwork_url") or ""),
            Kind.FANART: _find_url(raw, ("channel_tvart_url", "channel_banner_url")),
        }
        for kind, url in urls.items():
            if kind in found or not url:
                continue
            if url.startswith("/") and hasattr(provider, "_url"):
                url = provider._url(url)
            try:
                remote = fetch_remote_artwork(
                    artwork_url=url,
                    provider=provider,
                    connection_provider=link.connection.provider,
                    max_bytes=MAX_ARTWORK_BYTES,
                )
            except Exception:  # noqa: BLE001 - artwork is optional
                remote = None
            extension = _IMAGE_TYPES.get(getattr(remote, "content_type", "")) if remote else None
            if remote is not None and extension and remote.body:
                found[kind] = (remote.body, extension)
        if Kind.POSTER in found:
            break
    return found


def _find_url(value: Any, keys: tuple[str, ...]) -> str:
    if isinstance(value, dict):
        for key in keys:
            if isinstance(value.get(key), str) and value[key]:
                return value[key]
        for item in value.values():
            found = _find_url(item, keys)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_url(item, keys)
            if found:
                return found
    return ""


def _artwork(projection, root: Path, action: Action) -> str:
    folder = str(PurePosixPath(action.path).parent)
    images = _channel_artwork(projection.library, action.channel)
    if Kind.POSTER not in images:
        raise _Conflict("No assigned integration returned artwork for this channel.")
    for kind, (data, extension) in images.items():
        name = "poster" if kind == Kind.POSTER else "fanart"
        relative = f"{folder}/{name}.{extension}"
        path = _target(root, relative, create_parents=True)
        recorded = ProjectionFile.objects.filter(projection=projection, relative_path=relative).first()
        current = _file_sha(path) if path.exists() else None
        if current not in (None, _sha(data)) and (recorded is None or not _is_ours(path, recorded)):
            # Someone else's image: never replaced.
            if kind == Kind.POSTER:
                raise _Conflict("A poster LibraryForge didn't create is already in this folder.")
            continue
        if current != _sha(data):
            _write_bytes(path, data)
        ProjectionFile.objects.update_or_create(
            projection=projection,
            relative_path=relative,
            defaults={"kind": kind, "channel": action.channel, "size_bytes": len(data), "content_sha256": _sha(data)},
        )
    return "artwork"




# ---------------------------------------------------------------------------
# Engine entry points
# ---------------------------------------------------------------------------


def _shows_overview(projection: Projection, planned: dict[str, Any], actions: list) -> dict[str, Any]:
    pending: dict[str, int] = {}
    videos: dict[str, int] = {}
    files: dict[str, int] = {}
    for action in planned["actions"]:
        if action.channel and action.action != "retain":
            pending[str(action.channel.id)] = pending.get(str(action.channel.id), 0) + 1
    for item in planned["desired"]:
        files[item.kind] = files.get(item.kind, 0) + 1
        if item.kind == Kind.VIDEO:
            videos[str(item.channel.id)] = videos.get(str(item.channel.id), 0) + 1
    return {
        "artwork_available": planned["has_artwork"],
        "files": files,
        "channels": [
            {
                "id": str(channel.id),
                "title": channel.title,
                "folder": planned["names"][channel.id],
                "rating": channel.content_rating,
                "videos": videos.get(str(channel.id), 0),
                "pending": pending.get(str(channel.id), 0),
            }
            for channel in planned["channels"]
        ],
    }


def plan(projection) -> dict[str, Any]:
    planned = _plan(projection)
    return {
        "actions": planned["actions"],
        "desired": planned["desired"],
        "findings": [],
        "overview": _shows_overview(projection, planned, planned["actions"]),
    }


def filter_scope(actions: list, scope_id: str | None) -> list:
    return _filtered(actions, scope_id)
