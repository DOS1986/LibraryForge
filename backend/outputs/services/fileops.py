"""Generic projection file operations, shared by every layout.

Planning lives in the layouts (``youtube_shows``, ``movies_tv``); the engine
journals and sequences runs. This module creates, updates, relinks, replaces,
and removes single output files safely:

* every path is joined through the validated destination root and confined
  after folders are created (no links or junctions leading out);
* media is placed by the projection's policy (hardlink, symlink, or copy);
* generated files are written atomically and recorded with their hash;
* a recorded file is only rewritten or removed while it's unchanged;
* an existing file is only adopted when the run journal allows it.
"""

from __future__ import annotations

import errno
import hashlib
import os
import re
import shutil
import subprocess
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from catalog.artwork_views import _attached_picture_stream, _ffmpeg_executable
from catalog.models import Channel
from media.models import MediaFile
from metadata.services import secure_nfo
from metadata.services.provider_match import MatchRequestError
from outputs.models import Projection, ProjectionFile

Kind = ProjectionFile.Kind
MAX_ART_BYTES = 25 * 1024 * 1024


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


_CROSS_DEVICE_WINERRORS = (17,)  # ERROR_NOT_SAME_DEVICE


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


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class Desired:
    path: str
    kind: str
    channel: Channel | None
    media_file: MediaFile | None = None
    content: bytes | None = None
    season: int | None = None
    episode: int | None = None
    stream_index: int | None = None
    # Artwork copied from the library: its library-relative path and fingerprint.
    source_path: str = ""
    fingerprint: str = ""
    # The movie, series, or channel this file belongs to.
    group_id: str = ""
    group_title: str = ""


@dataclass
class Action:
    action: str
    kind: str
    path: str
    channel: Channel | None
    desired: Desired | None = None
    row: ProjectionFile | None = None
    group_id: str = ""
    group_title: str = ""

    def __post_init__(self) -> None:
        if not self.group_id and self.desired is not None:
            self.group_id, self.group_title = self.desired.group_id, self.desired.group_title
        if not self.group_id and self.channel is not None:
            self.group_id, self.group_title = str(self.channel.id), self.channel.title

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


class _Conflict(Exception):
    pass


class _CrossDevice(Exception):
    pass


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


def _place(projection, source: Path, destination: Path) -> None:
    """Put the media at ``destination`` by the projection's media policy."""

    mode = projection.link_mode
    if mode == Projection.LinkMode.HARDLINK:
        _link(source, destination)
    elif mode == Projection.LinkMode.SYMLINK:
        os.symlink(source, destination)
    else:
        # A copy is written beside the destination, size-checked, then renamed into place.
        temporary = destination.with_name(f".libraryforge-{uuid.uuid4().hex}.tmp")
        try:
            shutil.copyfile(source, temporary)
            if temporary.stat().st_size != source.stat().st_size:
                raise OSError("The copied file's size doesn't match the source.")
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()


def _matches_source(projection, source: Path, destination: Path) -> bool:
    """Whether ``destination`` already is this source under the media policy."""

    if projection.link_mode == Projection.LinkMode.HARDLINK:
        return _same_file(source, destination)
    if projection.link_mode == Projection.LinkMode.SYMLINK:
        try:
            return destination.is_symlink() and Path(os.readlink(destination)) == source
        except OSError:
            return False
    try:
        return destination.stat().st_size == source.stat().st_size
    except OSError:
        return False


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
            "source_fingerprint": desired.fingerprint,
        },
    )


def _library_file(library_root: Path, relative: str) -> Path:
    parts = PurePosixPath(str(relative).replace("\\", "/")).parts
    if not parts or ".." in parts:
        raise _Conflict("The source path is invalid.")
    path = library_root.joinpath(*parts).resolve(strict=True)
    if not path.is_relative_to(library_root) or not path.is_file():
        raise _Conflict("The source file isn't inside the library.")
    return path


def _generated_bytes(library_root: Path, desired: Desired) -> bytes:
    """The bytes a generated or copied file should contain."""

    if desired.kind == Kind.THUMB:
        return _thumbnail(_source(library_root, desired.media_file), desired.media_file, desired.stream_index)
    if desired.kind == Kind.ART:
        source = _library_file(library_root, desired.source_path)
        if source.stat().st_size > MAX_ART_BYTES:
            raise _Conflict("The artwork file is too large to copy.")
        return source.read_bytes()
    return desired.content or b""


def _create(projection, root: Path, library_root: Path, desired: Desired, *, allow_adopt: bool = False) -> str:
    """Create one file. An existing file is only adopted when the run journal
    shows an earlier run of this projection was creating it (``allow_adopt``)."""

    path = _target(root, desired.path, create_parents=True)
    if desired.kind == Kind.VIDEO:
        source = _source(library_root, desired.media_file)
        if path.exists():
            if not allow_adopt or not _matches_source(projection, source, path):
                raise _Conflict("A file LibraryForge didn't create is already at this path.")
            _record(projection, desired.path, desired, size=source.stat().st_size)
            return "adopted"
        _place(projection, source, path)
        _record(projection, desired.path, desired, size=source.stat().st_size)
        return "created"

    data = _generated_bytes(library_root, desired)
    if path.exists():
        # Left by an interrupted run: adopt it only if it's exactly what we'd write.
        if not allow_adopt or _file_sha(path) != _sha(data):
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


def _apply(projection, root: Path, library_root: Path, action: Action, *, allow_adopt: bool = False) -> str:
    if action.action == ACTION_CREATE:
        return _create(projection, root, library_root, action.desired, allow_adopt=allow_adopt)
    if action.action == ACTION_ARTWORK:
        # Remote channel artwork belongs to the online-video layout.
        from outputs.services.youtube_shows import _artwork

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
            if _matches_source(projection, source, path):
                _record(projection, action.path, action.desired, size=source.stat().st_size)
                return "relinked"
            if not _is_ours(path, row):
                raise _Conflict("The linked video changed outside LibraryForge, so it was left alone.")
            path.unlink()
        _place(projection, source, path)
        _record(projection, action.path, action.desired, size=source.stat().st_size)
        return "relinked"

    # Update or replace: only an unchanged file of ours is rewritten.
    if path.exists():
        if not _is_ours(path, row):
            raise _Conflict("This file was changed outside LibraryForge, so it was left alone.")
        if action.action == ACTION_UPDATE:
            data = _generated_bytes(library_root, action.desired)
            _write_bytes(path, data)
            _record(projection, action.path, action.desired, size=len(data), sha=_sha(data))
            return "updated"
        path.unlink()
    row.delete()
    result = _create(projection, root, library_root, action.desired, allow_adopt=allow_adopt)
    return "updated" if result == "created" else result


def diff(desired: list[Desired], manifest: dict[str, ProjectionFile], *, keep: set[str] | None = None) -> list[Action]:
    """Actions that turn the manifest into ``desired`` (shared by layouts).

    Paths that differ only by letter case keep the recorded spelling, so a
    case-insensitive share never sees a create-then-delete of one file.
    ``keep`` lists manifest paths a layout still owns but didn't list.
    """

    folded = {path.casefold(): path for path in manifest}
    wanted = set(keep or ())
    actions: list[Action] = []
    for item in desired:
        item.path = folded.get(item.path.casefold(), item.path)
        wanted.add(item.path)
        row = manifest.get(item.path)
        if row is None:
            actions.append(Action(ACTION_CREATE, item.kind, item.path, item.channel, item))
        elif row.kind != item.kind or (item.kind == Kind.VIDEO and row.media_file_id != item.media_file.id):
            actions.append(Action(ACTION_REPLACE, item.kind, item.path, item.channel, item, row))
        elif item.kind == Kind.VIDEO and row.size_bytes != item.media_file.size_bytes:
            actions.append(Action(ACTION_RELINK, item.kind, item.path, item.channel, item, row))
        elif (item.content is not None and row.content_sha256 != _sha(item.content)) or (
            item.kind == Kind.ART and row.source_fingerprint != item.fingerprint
        ):
            actions.append(Action(ACTION_UPDATE, item.kind, item.path, item.channel, item, row))
    for path, row in manifest.items():
        if path not in wanted:
            actions.append(
                Action(ACTION_DELETE, row.kind, path, row.channel, row=row, group_id=str(row.channel_id or ""))
            )
    actions.sort(key=lambda action: action.sort_key)
    return actions
