"""NFOs and artwork written into the library itself.

The in-place counterpart of the movie and TV projections, for Sidecar Only
and Full Control libraries (Read Only is refused when planning and again
when running). It runs through the same reviewed plans, background runs,
journal, and history as projections; the projection row only names the
library and the output profile.

NFOs use the alpha.5 field-level writer (``metadata.services.nfo_fields``):

* **Missing NFOs** are created beside the item, named as the media servers
  read them (``<file>.nfo``, ``tvshow.nfo`` in the series folder).
* **Existing NFOs** get only the fields LibraryForge has a different value
  for. Every other tag, comment, and the file's formatting are kept byte for
  byte, and a value only the NFO has is never erased. The plan stores the
  exact new text. The run writes it only if the file is still byte for byte
  what the plan read.
* NFOs that don't parse, changed on disk since the last scan, or exist but
  aren't indexed yet are left alone and reported.

Artwork: each selected image is copied into the item's folder under the
profile's name (``poster.jpg``; ``<file>-poster.jpg`` for Kodi movies;
``season01-poster.jpg`` in the show folder for Kodi seasons;
``<file>-thumb.jpg`` for episodes):

* An image already in place under that name, with the same bytes, is left
  as it is.
* A different file at that name is kept as
  ``<name>.libraryforge-backup-<time>.<ext>``, which neither the media
  servers nor LibraryForge's scanner treat as artwork. A copy LibraryForge
  made earlier is replaced without a backup if it's unchanged.
* Copies that are no longer wanted are removed only if LibraryForge made
  them and they're unchanged, and only when removal is safe: the last scan
  finished and the library is reachable.
* Movies sharing a folder get artwork only under Kodi's file-named
  convention.
* Seasons without a folder of their own get artwork only under Kodi's
  show-folder convention.

Nothing outside the library root is written. Planning reads files; it
writes none.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

from django.utils import timezone

from catalog.models import ArtworkFile, Episode, Series
from catalog.services.artwork import _build_location_index, is_embedded_artwork_path
from libraries.models import Library
from media.models import MediaItem
from metadata.models import NfoFile
from metadata.services import nfo_fields as nf
from metadata.services import secure_nfo
from metadata.services.provider_artwork import _backup_name
from outputs.models import Projection, ProjectionFile, ProjectionPlanAction
from outputs.services import profiles
from outputs.services.fileops import (
    ACTION_CREATE,
    ACTION_DELETE,
    ACTION_REPLACE,
    ACTION_UPDATE,
    Action,
    Desired,
    _Conflict,
    _file_sha,
    _library_file,
)
from outputs.services.movies_tv import _extension, _primary_files

Kind = ProjectionFile.Kind
Art = ArtworkFile.ArtworkType
RETAIN = ProjectionPlanAction.Action.RETAIN

NFO_KINDS = {"movie": Kind.MOVIE_NFO, "series": Kind.SHOW_NFO, "episode": Kind.EPISODE_NFO}
MAX_ART_BYTES = 25 * 1024 * 1024

MESSAGES = {
    "NO_FILE": "{n} movie(s) or episode(s) have no file in the library right now, so they get no NFO or artwork.",
    "NO_FOLDER": "{n} series have no folder of their own that LibraryForge can find. Rescan the library.",
    "UNPARSEABLE": "{n} NFO(s) couldn't be parsed and are left alone. Fix them with the raw editor on the NFO page.",
    "CHANGED_ON_DISK": "{n} NFO(s) changed on disk since the last scan and are left alone. Rescan the library first.",
    "UNINDEXED": "{n} file(s) exist on disk but aren't indexed yet, so they're left alone. Rescan the library first.",
    "UNREADABLE": "{n} file(s) couldn't be read and are left alone.",
    "SHARED_FOLDER": (
        "{n} movie image(s) skipped: the movie shares its folder with others, so a poster.jpg there would apply to "
        "all of them. Give each movie its own folder (or use the Kodi profile, which names art after the file)."
    ),
    "SEASON_FOLDER": (
        "{n} season image(s) skipped: the season has no folder of its own (or use the Kodi profile, which keeps "
        "season art in the show folder)."
    ),
    "STALE_KEPT": "{n} earlier artwork copy(ies) are no longer selected but are kept for now: {reason}",
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _join(folder: str, name: str) -> str:
    return name if folder in ("", ".") else f"{folder}/{name}"


def _confined(library_root: Path, relative: str, *, must_exist: bool = False) -> Path:
    """The library path for ``relative``; its folder must already exist inside the library."""

    parts = PurePosixPath(str(relative).replace("\\", "/")).parts
    if not parts or ".." in parts or PurePosixPath(relative).is_absolute():
        raise _Conflict("The path is invalid.")
    parent = library_root.joinpath(*parts[:-1]).resolve(strict=True)
    if not (parent == library_root or parent.is_relative_to(library_root)) or not parent.is_dir():
        raise _Conflict("The folder isn't inside the library.")
    path = parent / parts[-1]
    if path.is_symlink():
        raise _Conflict("A link is in the way; it's left alone.")
    if must_exist and not path.is_file():
        raise _Conflict("The file is gone.")
    return path


# ---------------------------------------------------------------------------
# Planning NFOs
# ---------------------------------------------------------------------------


class _Lookup:
    """Everything planning needs about a library, loaded once."""

    def __init__(self, library: Library):
        from metadata.services.nfo_ratings import _series_sources

        self.library = library
        self.index = _build_location_index(library)
        self.movies = list(MediaItem.objects.filter(library=library, media_type=MediaItem.MediaType.MOVIE).order_by("title", "id"))
        self.series = list(Series.objects.filter(library=library).order_by("title", "id"))
        self.episodes = list(
            Episode.objects.filter(season__series__library=library)
            .select_related("season", "season__series", "media_item")
            .order_by("season__series__title", "season__season_number", "episode_number", "id")
        )
        self.files = _primary_files(self.movies + [episode.media_item for episode in self.episodes])
        nfos = list(NfoFile.objects.filter(library=library, is_present=True).order_by("relative_path"))
        self.nfo_by_item: dict[tuple, NfoFile] = {}
        self.nfo_by_path = {nfo.relative_path.casefold(): nfo for nfo in nfos}
        for nfo in nfos:
            if nfo.media_item_id:
                self.nfo_by_item.setdefault((nfo.media_item_id, nfo.root_element), nfo)
        self.series_nfos = _series_sources(library)[0]
        self.series_folders: dict[Any, list[str]] = defaultdict(list)
        for folder, series_id in self.index["series_dirs"].items():
            self.series_folders[series_id].append(folder)
        self.season_folders: dict[Any, list[str]] = defaultdict(list)
        for folder, season_id in self.index["season_dirs"].items():
            self.season_folders[season_id].append(folder)

    def series_folder(self, series_id) -> str | None:
        folders = self.series_folders.get(series_id) or []
        return folders[0] if len(folders) == 1 else None


def _nfo_action(lookup: _Lookup, library_root: Path, kind: str, obj, counts) -> Action | None:
    library = lookup.library
    root = nf.ROOTS[kind]
    if kind == "series":
        title, group = obj.title, (str(obj.id), obj.title)
        folder = lookup.series_folder(obj.id)
        planned = None if folder is None else _join(folder, "tvshow.nfo")
        media_file = None
        existing = (lookup.series_nfos.get(obj.id) or [None])[0]
        missing_code = "NO_FOLDER"
    else:
        item = obj if kind == "movie" else obj.media_item
        title = item.title
        series = obj.season.series if kind == "episode" else None
        group = (str(series.id), series.title) if series else (str(item.id), item.title)
        media_file = lookup.files.get(item.id)
        planned = PurePosixPath(media_file.relative_path.replace("\\", "/")).with_suffix(".nfo").as_posix() if media_file else None
        existing = lookup.nfo_by_item.get((item.id, root))
        missing_code = "NO_FILE"
    if existing is None and planned:
        existing = lookup.nfo_by_path.get(planned.casefold())

    target = nf.Target(kind, obj, library, title)
    values = nf.catalog_values(target)
    common = {"channel": None, "media_file": media_file, "group_id": group[0], "group_title": group[1]}

    if existing is None:
        if not planned:
            counts[missing_code] += 1
            return None
        if not any(values.values()):
            return None
        try:
            if _confined(library_root, planned).exists():
                counts["UNINDEXED"] += 1
                return None
        except (_Conflict, OSError):
            counts["UNREADABLE"] += 1
            return None
        content = nf.build_nfo(root, values)
        nf._verify(content, root, {tag: value for tag, value in values.items() if value})
        desired = Desired(
            path=planned, kind=NFO_KINDS[kind], content=content.encode("utf-8"),
            extra={"target_kind": kind, "target_id": str(obj.id)}, **common,
        )
        return Action(ACTION_CREATE, desired.kind, planned, None, desired, reason="New NFO from LibraryForge's metadata")

    if existing.parse_status != NfoFile.ParseStatus.OK or existing.root_element != root:
        counts["UNPARSEABLE"] += 1
        return None
    try:
        current_fields = nf.read_nfo_fields(existing.raw_xml, root)
    except ValueError:
        counts["UNPARSEABLE"] += 1
        return None
    updates: dict[str, Any] = {}
    labels = []
    for field in nf.FIELDS[kind]:
        if nf._status(values[field.tag], current_fields.get(field.tag), field) in ("different", "missing"):
            updates[field.tag] = values[field.tag]
            labels.append(field.label.lower())
    if not updates:
        return None
    try:
        current = nf._read_current(existing)
    except OSError:
        counts["UNREADABLE"] += 1
        return None
    if current is None:
        counts["CHANGED_ON_DISK"] += 1
        return None
    try:
        updated = nf.set_nfo_fields(current, root, updates)
        nf._verify(updated, root, updates)
    except ValueError:
        counts["UNPARSEABLE"] += 1
        return None
    desired = Desired(
        path=existing.relative_path, kind=NFO_KINDS[kind], content=updated.encode("utf-8"),
        extra={"nfo_id": str(existing.id), "before_sha256": _sha(current), "fields": sorted(updates)}, **common,
    )
    return Action(ACTION_UPDATE, desired.kind, existing.relative_path, None, desired, reason=f"Update {', '.join(labels)}")


# ---------------------------------------------------------------------------
# Planning artwork
# ---------------------------------------------------------------------------


def _places(lookup: _Lookup, profile: profiles.Profile, counts) -> list[tuple[ArtworkFile, str, str, Any, tuple[str, str]]]:
    """(artwork, folder, file stem, media file, group) for every selected image to place."""

    library = lookup.library
    selected: dict[tuple, list[ArtworkFile]] = defaultdict(list)
    for artwork in ArtworkFile.objects.filter(library=library, is_selected=True, is_present=True).order_by(
        "artwork_type", "relative_path"
    ):
        if not is_embedded_artwork_path(artwork.relative_path):
            selected[(artwork.target_type, artwork.target_id)].append(artwork)

    places = []
    for item in lookup.movies:
        artworks = [a for a in selected.get((ArtworkFile.TargetType.MEDIA_ITEM, item.id), []) if a.artwork_type in profile.art]
        if not artworks:
            continue
        media_file = lookup.files.get(item.id)
        if media_file is None:
            continue
        path = PurePosixPath(media_file.relative_path.replace("\\", "/"))
        folder = path.parent.as_posix()
        own = lookup.index["movie_dirs"].get(folder) == item.id
        for artwork in artworks:
            if profile.movie_art_prefix:
                stem = profile.movie_art(path.stem, artwork.artwork_type)
            elif own:
                stem = profile.art[artwork.artwork_type]
            else:
                counts["SHARED_FOLDER"] += 1
                continue
            places.append((artwork, folder, stem, media_file, (str(item.id), item.title)))

    episodes_by_season: dict[Any, list] = defaultdict(list)
    for episode in lookup.episodes:
        episodes_by_season[episode.season_id].append(episode)
    for series in lookup.series:
        group = (str(series.id), series.title)
        show = lookup.series_folder(series.id)
        artworks = [a for a in selected.get((ArtworkFile.TargetType.SERIES, series.id), []) if a.artwork_type in profile.art]
        if artworks and show is None:
            counts["NO_FOLDER"] += 1
        for artwork in artworks if show is not None else []:
            places.append((artwork, show, profile.art[artwork.artwork_type], None, group))
        for season in {episode.season for episode in lookup.episodes if episode.season.series_id == series.id}:
            artworks = [a for a in selected.get((ArtworkFile.TargetType.SEASON, season.id), []) if a.artwork_type in profile.art]
            if not artworks:
                continue
            own = lookup.season_folders.get(season.id) or []
            season_folder = own[0] if len(own) == 1 else None
            for artwork in artworks:
                if profile.season_art_in_show_folder and show is not None:
                    folder, stem = profile.season_art(show, "", season.season_number, artwork.artwork_type)
                elif season_folder is not None and not profile.season_art_in_show_folder:
                    folder, stem = season_folder, profile.art[artwork.artwork_type]
                else:
                    counts["SEASON_FOLDER"] += 1
                    continue
                places.append((artwork, folder, stem, None, group))

    for episode in lookup.episodes:
        thumbs = [a for a in selected.get((ArtworkFile.TargetType.EPISODE, episode.id), []) if a.artwork_type in (Art.PRIMARY, Art.THUMB)]
        media_file = lookup.files.get(episode.media_item_id)
        if not thumbs or media_file is None:
            continue
        path = PurePosixPath(media_file.relative_path.replace("\\", "/"))
        series = episode.season.series
        places.append((thumbs[0], path.parent.as_posix(), f"{path.stem}-thumb", media_file, (str(series.id), series.title)))
    return places


def _art_actions(projection: Projection, lookup: _Lookup, library_root: Path, profile, counts) -> list[Action]:
    manifest = {row.relative_path.casefold(): row for row in ProjectionFile.objects.filter(projection=projection)}
    wanted: set[str] = set()
    sources = {artwork.relative_path.casefold() for artwork in ArtworkFile.objects.filter(library=lookup.library, is_present=True)}
    actions = []
    for artwork, folder, stem, media_file, group in _places(lookup, profile, counts):
        extension = _extension(artwork.extension or PurePosixPath(artwork.relative_path).suffix)
        relative = _join(folder, f"{stem}.{extension}")
        key = relative.casefold()
        if key in wanted:
            continue
        wanted.add(key)
        if key == artwork.relative_path.casefold():
            continue  # The selected image already has this name.
        fingerprint = f"{artwork.relative_path}|{artwork.size_bytes}|{artwork.modified_ns}"
        row = manifest.get(key)
        try:
            target = _confined(library_root, relative)
            exists = target.exists()
            state: dict[str, Any] = {"exists": exists}
            if exists:
                size = target.stat().st_size
                if row is not None and row.source_fingerprint == fingerprint and row.size_bytes == size:
                    continue  # Our copy of this very image.
                sha = _file_sha(target)
                source = _library_file(library_root, artwork.relative_path)
                if source.stat().st_size == size and _file_sha(source) == sha:
                    continue  # Already the same image.
                state.update(size=size, sha256=sha)
        except (_Conflict, OSError):
            counts["UNREADABLE"] += 1
            continue
        if not exists:
            action, reason = ACTION_CREATE, "Copy of the selected image"
        elif row is not None and state["sha256"] == row.content_sha256:
            action, reason = ACTION_UPDATE, "The selected image changed"
        else:
            action, reason = ACTION_REPLACE, "A different image is there; it's kept as a backup"
        desired = Desired(
            path=relative, kind=Kind.ART, channel=None, media_file=media_file, source_path=artwork.relative_path,
            fingerprint=fingerprint, group_id=group[0], group_title=group[1], extra={"target": state},
        )
        actions.append(Action(action, Kind.ART, relative, None, desired, row, reason=reason))

    stale = [row for key, row in manifest.items() if key not in wanted and key not in sources]
    if stale:
        from outputs.services.engine import _removals_allowed

        allowed, why = _removals_allowed(projection)
        for row in stale:
            if allowed:
                actions.append(Action(ACTION_DELETE, row.kind, row.relative_path, None, row=row, reason="LibraryForge's earlier copy isn't selected anymore"))
            else:
                actions.append(Action(RETAIN, row.kind, row.relative_path, None, row=row, reason="Kept until removal is safe"))
        if not allowed:
            counts["STALE_KEPT"] += len(stale)
            counts["_stale_reason"] = why  # type: ignore[assignment]
    return actions


# ---------------------------------------------------------------------------
# Engine entry points
# ---------------------------------------------------------------------------


def plan(projection: Projection) -> dict[str, Any]:
    library = projection.library
    profile = profiles.for_target(projection.output_profile.target)
    library_root = Path(library.path).expanduser().resolve(strict=True)
    lookup = _Lookup(library)
    counts: dict[str, Any] = defaultdict(int)

    actions: list[Action] = []
    for kind, objects in (("movie", lookup.movies), ("series", lookup.series), ("episode", lookup.episodes)):
        for obj in objects:
            action = _nfo_action(lookup, library_root, kind, obj, counts)
            if action is not None:
                actions.append(action)
    actions.extend(_art_actions(projection, lookup, library_root, profile, counts))
    actions.sort(key=lambda action: action.sort_key)

    reason = counts.pop("_stale_reason", "")
    findings = [
        {"code": code, "severity": "warning", "message": MESSAGES[code].format(n=counts[code], reason=reason)}
        for code in MESSAGES
        if counts.get(code)
    ]
    nfo_changes = sum(1 for action in actions if action.kind in NFO_KINDS.values())
    overview = {
        "movies": len(lookup.movies),
        "series_count": len(lookup.series),
        "episodes": len(lookup.episodes),
        "nfo_changes": nfo_changes,
        "art_changes": len(actions) - nfo_changes,
        "skipped": sum(counts.get(code, 0) for code in MESSAGES if code != "STALE_KEPT"),
    }
    return {"actions": actions, "desired": [a.desired for a in actions if a.desired is not None], "findings": findings, "overview": overview}


def filter_scope(actions: list, scope_id: str | None) -> list:
    if not scope_id:
        return actions
    return [action for action in actions if action.group_id == str(scope_id)]


def policy_findings(projection: Projection) -> list[dict[str, str]]:
    library = projection.library
    findings = []
    if library.management_mode == Library.ManagementMode.READ_ONLY:
        findings.append(
            {
                "code": "LIBRARY_READ_ONLY",
                "severity": "blocking",
                "message": "This library is Read Only, so LibraryForge can't write NFOs or artwork into it. Change its "
                "management mode to Sidecar Only to allow it.",
            }
        )
    if library.content_type == "online_video":
        findings.append(
            {
                "code": "UNSUPPORTED_LIBRARY",
                "severity": "blocking",
                "message": "Online video NFOs belong in the Channels as TV shows folder, not in TubeArchivist's.",
            }
        )
    problem = secure_nfo.library_root_error(library)
    if problem:
        findings.append({"code": "SOURCE_UNAVAILABLE", "severity": "blocking", "message": problem})
    return findings


# ---------------------------------------------------------------------------
# Applying one reviewed action
# ---------------------------------------------------------------------------


def apply_record(projection: Projection, record, library_root: Path) -> tuple[str, str]:
    """Apply one plan action in place. Returns (result, note); raises _Conflict to leave it alone."""

    library = projection.library
    if library.management_mode == Library.ManagementMode.READ_ONLY:
        raise _Conflict("The library is Read Only now.")
    try:
        if record.kind in NFO_KINDS.values():
            return _create_nfo(library, record) if record.action == ACTION_CREATE else _update_nfo(library, record)
        if record.action == ACTION_DELETE:
            return _delete_copy(projection, record, library_root)
        return _copy_art(projection, record, library_root)
    except ValueError as error:
        raise _Conflict(str(error) or "The file couldn't be written.") from error


def _create_nfo(library: Library, record) -> tuple[str, str]:
    relative = record.relative_path
    nfo = NfoFile.objects.filter(library=library, relative_path=relative).first()
    if nfo is not None and nfo.is_present:
        raise _Conflict("An NFO was indexed at this path since the plan was built. Build a new plan.")
    probe = nfo or NfoFile(library=library, relative_path=relative, file_name=PurePosixPath(relative).name)
    if secure_nfo._destination_for(probe).exists():
        raise _Conflict("A file appeared at this path since the plan was built. Rescan the library, then build a new plan.")
    media_file = record.media_file
    if nfo is None:
        nfo = NfoFile(library=library, relative_path=relative, file_name=PurePosixPath(relative).name, is_generated=True)
    nfo.media_item = media_file.media_item if media_file is not None else None
    nfo.media_file = media_file
    secure_nfo.write_nfo_file(nfo, record.content)
    return "created", ""


def _update_nfo(library: Library, record) -> tuple[str, str]:
    nfo = NfoFile.objects.filter(id=record.desired.get("nfo_id"), library=library, is_present=True).first()
    if nfo is None:
        raise _Conflict("The NFO isn't indexed anymore. Rescan the library, then build a new plan.")
    current = nf._read_current(nfo)
    if current is None or _sha(current) != record.desired.get("before_sha256"):
        raise _Conflict("The NFO changed since the plan was built. Build a new plan.")
    secure_nfo.write_nfo_file(nfo, record.content)
    return "updated", ""


def _copy_art(projection: Projection, record, library_root: Path) -> tuple[str, str]:
    source = _library_file(library_root, record.desired.get("source_path") or "")
    stat = source.stat()
    if f"{record.desired.get('source_path')}|{stat.st_size}|{stat.st_mtime_ns}" != record.desired.get("fingerprint"):
        raise _Conflict("The selected image changed since the plan was built. Build a new plan.")
    if stat.st_size > MAX_ART_BYTES:
        raise _Conflict("The image is too large to copy.")
    data = source.read_bytes()

    target = _confined(library_root, record.relative_path)
    expected = record.desired.get("target") or {}
    if target.exists() != bool(expected.get("exists")):
        raise _Conflict("A file appeared or went away at this path since the plan was built. Build a new plan.")
    if target.exists() and (target.stat().st_size != expected.get("size") or _file_sha(target) != expected.get("sha256")):
        raise _Conflict("The file at this path changed since the plan was built. Build a new plan.")

    note, backup = "", None
    temporary = target.parent / f".libraryforge-{uuid.uuid4().hex}.tmp"
    try:
        if record.action == ACTION_REPLACE and target.exists():
            backup = target.parent / _backup_name(target.parent, target.name, timezone.now().strftime("%Y%m%d%H%M%S"))
            os.replace(target, backup)
            note = f"Kept the previous file as {backup.name}."
        with temporary.open("xb") as handle:
            handle.write(data)
        os.replace(temporary, target)
    except BaseException:
        if temporary.exists():
            temporary.unlink()
        if backup is not None and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    written = target.stat()
    ProjectionFile.objects.update_or_create(
        projection=projection,
        relative_path=record.relative_path,
        defaults={
            "kind": Kind.ART,
            "media_file": record.media_file,
            "size_bytes": written.st_size,
            "content_sha256": hashlib.sha256(data).hexdigest(),
            "source_fingerprint": record.desired.get("fingerprint") or "",
            "ownership": ProjectionFile.Ownership.OWNED,
        },
    )
    result = {ACTION_CREATE: "created", ACTION_UPDATE: "updated"}.get(record.action, "replaced")
    return result, note


def _delete_copy(projection: Projection, record, library_root: Path) -> tuple[str, str]:
    row = ProjectionFile.objects.filter(id=record.manifest_file_id, projection=projection).first()
    if row is None:
        return "deleted", ""
    try:
        target = _confined(library_root, row.relative_path)
    except (_Conflict, OSError):
        row.delete()
        return "deleted", ""
    if not target.exists():
        row.delete()
        return "deleted", ""
    if _file_sha(target) != row.content_sha256:
        row.delete()
        return "kept", "Changed outside LibraryForge, so it was left in place."
    target.unlink()
    row.delete()
    return "deleted", ""
