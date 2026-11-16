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

import errno
import hashlib
import os
import re
import subprocess
import uuid
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from django.db import DatabaseError, transaction
from django.utils import timezone

from catalog.artwork_views import _attached_picture_stream, _ffmpeg_executable
from catalog.models import ArtworkFile, Channel
from catalog.services.artwork import embedded_artwork_locator
from integrations.security import fetch_remote_artwork
from integrations.services import active_links_for_library, provider_for_connection
from media.models import MediaFile
from metadata.services import secure_nfo
from metadata.services.provider_match import MatchRequestError
from outputs.models import Projection, ProjectionFile

Kind = ProjectionFile.Kind

MAX_SHOW_NAME = 60
MAX_TITLE = 80
DEFAULT_BATCH = 25
MAX_BATCH = 200
SAMPLE_LIMIT = 200
MAX_ARTWORK_BYTES = 15 * 1024 * 1024
MAX_THUMB_BYTES = 25 * 1024 * 1024

ACTION_CREATE = "create"
ACTION_UPDATE = "update"
ACTION_RELINK = "relink"
ACTION_REPLACE = "replace"
ACTION_DELETE = "delete"
ACTION_ARTWORK = "artwork"
ACTIONS = (ACTION_CREATE, ACTION_UPDATE, ACTION_RELINK, ACTION_REPLACE, ACTION_DELETE, ACTION_ARTWORK)

RESULTS = ("created", "updated", "relinked", "deleted", "artwork", "adopted", "kept", "conflict", "failed")

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
_XML_INVALID = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_EXTENSION = re.compile(r"^[a-z0-9]{1,8}$")
_IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
_CROSS_DEVICE_WINERRORS = (17,)  # ERROR_NOT_SAME_DEVICE


# ---------------------------------------------------------------------------
# Names and NFO documents
# ---------------------------------------------------------------------------


def safe_segment(value: Any, limit: int) -> str:
    """A single file or folder name that's valid on Windows, Linux, and SMB."""

    text = " ".join(_INVALID.sub("_", str(value or "")).split())
    text = text[:limit].strip().strip(". ")
    if not text:
        return "Untitled"
    if text.split(".")[0].casefold() in _RESERVED:
        text = f"_{text}"
    return text


def _clean(value: Any) -> str:
    return _XML_INVALID.sub("", str(value or "")).strip()


def _xml(root_name: str, fields: list[tuple[str, Any, dict[str, str]]]) -> bytes:
    root = ET.Element(root_name)
    for tag, value, attributes in fields:
        text = _clean(value)
        if text:
            ET.SubElement(root, tag, attributes).text = text
    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode")
    return f'<?xml version="1.0" encoding="utf-8" standalone="yes"?>\n{body}\n'.encode()


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


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Planning (database only)
# ---------------------------------------------------------------------------


@dataclass
class Desired:
    path: str
    kind: str
    channel: Channel
    media_file: MediaFile | None = None
    content: bytes | None = None
    season: int | None = None
    episode: int | None = None
    stream_index: int | None = None


@dataclass
class Action:
    action: str
    kind: str
    path: str
    channel: Channel | None
    desired: Desired | None = None
    row: ProjectionFile | None = None

    @property
    def sort_key(self) -> str:
        # Show files first, deletions last, so a renamed video is linked
        # under its new name before the old name is removed.
        phase = 2 if self.action == ACTION_DELETE else (0 if self.kind in (Kind.SHOW_NFO, "artwork") else 1)
        return f"{phase}\x00{self.path}"

    def summary(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "kind": self.kind,
            "path": self.path,
            "channel_id": str(self.channel.id) if self.channel else None,
            "channel": self.channel.title if self.channel else "",
        }


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


def destination_error(projection) -> str | None:
    """None if the destination folder exists or can be created, else why not."""

    try:
        destination = Path(projection.destination_path).expanduser()
        if destination.exists():
            return None if destination.is_dir() else "The destination isn't a folder."
        if not destination.parent.is_dir():
            return f"The destination's parent folder ({destination.parent}) doesn't exist."
    except OSError as exc:
        return secure_nfo.library_root_problem(exc)
    return None


def shows_plan(projection, *, channel: str | None = None) -> dict[str, Any]:
    _require_layout(projection)
    plan = _plan(projection)
    actions = _filtered(plan["actions"], channel)
    summary = dict.fromkeys(ACTIONS, 0)
    for action in actions:
        summary[action.action] += 1

    files = dict.fromkeys(Kind.values, 0)
    for item in plan["desired"]:
        files[item.kind] += 1
    pending_by_channel: dict[str, int] = defaultdict(int)
    videos_by_channel: dict[str, int] = defaultdict(int)
    for action in plan["actions"]:
        if action.channel:
            pending_by_channel[str(action.channel.id)] += 1
    for item in plan["desired"]:
        if item.kind == Kind.VIDEO:
            videos_by_channel[str(item.channel.id)] += 1

    library = projection.library
    return {
        "projection_id": str(projection.id),
        "destination_path": projection.destination_path,
        "channel": channel or None,
        "source_error": secure_nfo.library_root_error(library),
        "destination_error": destination_error(projection),
        "artwork_available": plan["has_artwork"],
        "summary": summary,
        "pending": len(actions),
        "files": files,
        "managed_files": ProjectionFile.objects.filter(projection=projection).count(),
        "channels": [
            {
                "id": str(value.id),
                "title": value.title,
                "folder": plan["names"][value.id],
                "rating": value.content_rating,
                "videos": videos_by_channel[str(value.id)],
                "pending": pending_by_channel[str(value.id)],
            }
            for value in plan["channels"]
        ],
        "actions": [action.summary() for action in actions[:SAMPLE_LIMIT]],
        "actions_truncated": len(actions) > SAMPLE_LIMIT,
        "last_run_at": projection.last_run_at.isoformat() if projection.last_run_at else None,
    }


# ---------------------------------------------------------------------------
# Applying (one batch at a time)
# ---------------------------------------------------------------------------


class _Conflict(Exception):
    pass


class _CrossDevice(Exception):
    pass


def _require_layout(projection) -> None:
    if projection.layout != Projection.Layout.YOUTUBE_SHOWS:
        raise MatchRequestError("This projection doesn't use the Channels as TV shows layout.")


def _destination_root(projection) -> Path:
    destination = Path(projection.destination_path).expanduser()
    if not destination.exists():
        destination.mkdir()
    root = destination.resolve(strict=True)
    if not root.is_dir():
        raise MatchRequestError("The destination isn't a folder.", status=409)
    return root


def _target(root: Path, relative: str, *, create_parents: bool) -> Path:
    parts = PurePosixPath(relative).parts
    if not parts or ".." in parts or PurePosixPath(relative).is_absolute():
        raise _Conflict("The destination path is invalid.")
    path = root.joinpath(*parts)
    if create_parents:
        path.parent.mkdir(parents=True, exist_ok=True)
    parent = path.parent.resolve(strict=False)
    # A junction or symlink inside the destination must not lead elsewhere.
    if not (parent == root or parent.is_relative_to(root)):
        raise _Conflict("The destination folder leads outside the projection folder.")
    if path.is_symlink():
        raise _Conflict("A link LibraryForge didn't create is at this path.")
    return path


def _source(library_root: Path, media_file: MediaFile) -> Path:
    parts = PurePosixPath(str(media_file.relative_path).replace("\\", "/")).parts
    if not parts or ".." in parts:
        raise _Conflict("The source path is invalid.")
    path = library_root.joinpath(*parts).resolve(strict=True)
    if not path.is_relative_to(library_root) or not path.is_file():
        raise _Conflict("The source file isn't inside the library.")
    return path


def _same_file(first: Path, second: Path) -> bool:
    try:
        a, b = first.stat(), second.stat()
    except OSError:
        return False
    if a.st_ino and b.st_ino:
        return a.st_ino == b.st_ino and a.st_dev == b.st_dev
    # Some network shares report no file IDs; hardlinks share size and time.
    return a.st_size == b.st_size and a.st_mtime_ns == b.st_mtime_ns


def _write_bytes(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".libraryforge-{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_ours(path: Path, row: ProjectionFile) -> bool:
    """The file still is what LibraryForge recorded writing."""

    if row.kind == Kind.VIDEO:
        return row.size_bytes is not None and path.stat().st_size == row.size_bytes
    return bool(row.content_sha256) and _file_sha(path) == row.content_sha256


def _link(source: Path, destination: Path) -> None:
    try:
        os.link(source, destination)
    except OSError as exc:
        if exc.errno == errno.EXDEV or getattr(exc, "winerror", None) in _CROSS_DEVICE_WINERRORS:
            raise _CrossDevice from exc
        raise


def _thumbnail(source: Path, media_file: MediaFile, stream_index: int) -> bytes:
    if _attached_picture_stream(media_file, stream_index) is None:
        raise _Conflict("The video has no embedded thumbnail.")
    command = [
        _ffmpeg_executable(), "-v", "error", "-i", str(source), "-map", f"0:{stream_index}",
        "-frames:v", "1", "-c:v", "mjpeg", "-q:v", "2", "-f", "image2pipe", "pipe:1",
    ]
    try:
        result = subprocess.run(command, capture_output=True, check=False, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise _Conflict("The thumbnail couldn't be read from the video.") from exc
    data = result.stdout
    if result.returncode != 0 or not data.startswith(b"\xff\xd8") or len(data) > MAX_THUMB_BYTES:
        raise _Conflict("The thumbnail couldn't be read from the video.")
    return data


def _record(projection, path: str, desired: Desired, *, size: int | None, sha: str = "") -> None:
    ProjectionFile.objects.update_or_create(
        projection=projection,
        relative_path=path,
        defaults={
            "kind": desired.kind,
            "media_file": desired.media_file,
            "channel": desired.channel,
            "season_number": desired.season,
            "episode_number": desired.episode,
            "size_bytes": size,
            "content_sha256": sha,
        },
    )


def _create(projection, root: Path, library_root: Path, desired: Desired) -> str:
    path = _target(root, desired.path, create_parents=True)
    if desired.kind == Kind.VIDEO:
        source = _source(library_root, desired.media_file)
        if path.exists():
            if not _same_file(source, path):
                raise _Conflict("A file LibraryForge didn't create is already at this path.")
            _record(projection, desired.path, desired, size=source.stat().st_size)
            return "adopted"
        _link(source, path)
        _record(projection, desired.path, desired, size=source.stat().st_size)
        return "created"

    if desired.kind == Kind.THUMB:
        data = _thumbnail(_source(library_root, desired.media_file), desired.media_file, desired.stream_index)
    else:
        data = desired.content or b""
    if path.exists():
        # Left by an interrupted sync: adopt it only if it's exactly what we'd write.
        if _file_sha(path) != _sha(data):
            raise _Conflict("A file LibraryForge didn't create is already at this path.")
        _record(projection, desired.path, desired, size=len(data), sha=_sha(data))
        return "adopted"
    _write_bytes(path, data)
    _record(projection, desired.path, desired, size=len(data), sha=_sha(data))
    return "created"


def _remove_ours(root: Path, row: ProjectionFile) -> bool:
    """Delete a manifest file if it's unchanged; False if it was kept."""

    path = _target(root, row.relative_path, create_parents=False)
    if path.exists():
        if not _is_ours(path, row):
            return False
        path.unlink()
    _prune(root, path.parent)
    return True


def _prune(root: Path, folder: Path) -> None:
    """Remove folders left empty, up to the destination root."""

    current = folder
    while current != root and current.is_relative_to(root):
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


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


def _apply(projection, root: Path, library_root: Path, action: Action) -> str:
    if action.action == ACTION_CREATE:
        return _create(projection, root, library_root, action.desired)
    if action.action == ACTION_ARTWORK:
        return _artwork(projection, root, action)
    if action.action == ACTION_DELETE:
        kept = not _remove_ours(root, action.row)
        action.row.delete()
        return "kept" if kept else "deleted"

    row = action.row
    path = _target(root, row.relative_path, create_parents=True)
    if action.action == ACTION_RELINK:
        source = _source(library_root, action.desired.media_file)
        if path.exists():
            if _same_file(source, path):
                _record(projection, action.path, action.desired, size=source.stat().st_size)
                return "relinked"
            if not _is_ours(path, row):
                raise _Conflict("The linked video changed outside LibraryForge, so it was left alone.")
            path.unlink()
        _link(source, path)
        _record(projection, action.path, action.desired, size=source.stat().st_size)
        return "relinked"

    # Update or replace: only an unchanged file of ours is rewritten.
    if path.exists():
        if not _is_ours(path, row):
            raise _Conflict("This file was changed outside LibraryForge, so it was left alone.")
        if action.action == ACTION_UPDATE:
            data = action.desired.content or b""
            _write_bytes(path, data)
            _record(projection, action.path, action.desired, size=len(data), sha=_sha(data))
            return "updated"
        path.unlink()
    row.delete()
    result = _create(projection, root, library_root, action.desired)
    return "updated" if result == "created" else result


def shows_sync(projection, *, cursor: str | None = None, batch: Any = None, channel: str | None = None) -> dict[str, Any]:
    """Apply one batch of the plan, in a stable order, starting after ``cursor``."""

    _require_layout(projection)
    library = projection.library
    if library.management_mode == library.ManagementMode.READ_ONLY:
        # Source files are only read, but a read-only library is a clear
        # signal not to build anything from it without changing that first.
        raise MatchRequestError(
            "This library is Read Only. Change its management mode to Sidecar Only to build a Jellyfin folder from it.",
            status=409,
        )
    try:
        size = int(batch) if batch not in (None, "") else DEFAULT_BATCH
    except (TypeError, ValueError) as exc:
        raise MatchRequestError("Batch must be a whole number.") from exc
    if not 1 <= size <= MAX_BATCH:
        raise MatchRequestError(f"Batch must be between 1 and {MAX_BATCH}.")
    for problem in (secure_nfo.library_root_error(library), destination_error(projection)):
        if problem:
            raise MatchRequestError(problem, status=409)

    try:
        with transaction.atomic():
            # One sync per destination at a time.
            Projection.objects.select_for_update(nowait=True).get(pk=projection.pk)
            return _sync_batch(projection, cursor=cursor, size=size, channel=channel)
    except DatabaseError as exc:
        if "lock" in str(exc).casefold() or "could not obtain" in str(exc).casefold():
            raise MatchRequestError("A sync for this folder is already running.", status=409) from exc
        raise


def _sync_batch(projection, *, cursor: str | None, size: int, channel: str | None) -> dict[str, Any]:
    library_root = Path(projection.library.path).expanduser().resolve(strict=True)
    try:
        root = _destination_root(projection)
    except OSError as exc:
        raise MatchRequestError(secure_nfo.library_root_problem(exc), status=409) from exc

    pending = _filtered(_plan(projection)["actions"], channel)
    if cursor:
        pending = [action for action in pending if action.sort_key > cursor]
    selected = pending[:size]

    counts = dict.fromkeys(RESULTS, 0)
    problems: list[dict[str, Any]] = []
    error = None
    done = 0
    for action in selected:
        try:
            with transaction.atomic():
                result = _apply(projection, root, library_root, action)
        except _CrossDevice:
            # Every link would fail the same way. Stop, keeping what this batch recorded.
            error = (
                "Hardlinks can't be made here: the Jellyfin folder has to be on the same share and volume as the "
                "library. Choose a destination next to the library folder."
            )
            break
        except _Conflict as exc:
            result = "conflict"
            problems.append({**action.summary(), "result": result, "message": str(exc)})
        except OSError as exc:
            result = "failed"
            problems.append({**action.summary(), "result": result, "message": exc.strerror or str(exc)})
        counts[result] += 1
        done += 1
        if result == "kept":
            problems.append(
                {**action.summary(), "result": result, "message": "Changed outside LibraryForge, so it was left in place."}
            )

    remaining = len(pending) - done
    projection.last_run_at = timezone.now()
    projection.save(update_fields=["last_run_at", "updated_at"])
    return {
        "projection_id": str(projection.id),
        "counts": counts,
        "problems": problems,
        "error": error,
        "next_cursor": selected[done - 1].sort_key if done and remaining > 0 and error is None else None,
        "remaining": remaining,
    }
