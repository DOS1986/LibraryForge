"""Movie and TV layouts for projections.

Folder and file names are the same for every profile; artwork names and
season-art placement come from the projection's profile
(``outputs.services.profiles``). The Jellyfin profile looks like this:

Movies::

    The Matrix (1999)/
      The Matrix (1999).mkv        hardlink (or copy/symlink) of the primary version
      The Matrix (1999).nfo        movie NFO from LibraryForge's metadata
      poster.jpg, fanart.jpg, logo.png, banner.jpg, landscape.jpg   selected artwork, copied

TV::

    Bluey (2018)/
      tvshow.nfo, poster.jpg, fanart.jpg, ...
      Season 01/
        poster.jpg                                   selected season artwork, copied
        Bluey S01E01 - Magic Xylophone.mkv
        Bluey S01E01 - Magic Xylophone.nfo           episodedetails NFO
        Bluey S01E01 - Magic Xylophone-thumb.jpg     selected episode thumbnail, copied

Names are made safe for Windows, Linux, and SMB. Two titles that would share
a folder get a stable suffix (an IMDb/TMDB/TVDB ID, else a short LibraryForge
ID), never a counter. Items that can't be projected correctly yet (no file
present, multi-episode files, duplicate episode numbers, overlong paths) are
skipped and reported, never guessed at.

Artwork is copied from the files LibraryForge selected for each item; nothing
is downloaded while planning or running.
"""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any

from catalog.models import ArtworkFile, Episode, MediaVersion, Series
from catalog.services.artwork import is_embedded_artwork_path
from catalog.services.canonical import _movie_year
from media.models import MediaItem
from metadata.services.nfo_fields import Target, catalog_values
from outputs.models import Projection, ProjectionFile
from outputs.services import profiles
from outputs.services.fileops import Desired, _xml, diff, safe_segment

Kind = ProjectionFile.Kind

MAX_NAME = 100
MAX_EPISODE_TITLE = 80
MAX_PATH = 250  # whole destination path, to stay clear of Windows' 260 limit

UNIQUE_IDS = ("imdb", "tmdb", "tvdb")
# Shows and episodes are matched by TVDB first, as their scrapers do.
TV_UNIQUE_IDS = ("tvdb", "tmdb", "imdb")


def _key(path: str) -> str:
    return unicodedata.normalize("NFC", path).casefold()


def _extension(value: str) -> str:
    value = (value or "").lower().lstrip(".")
    return value if value.isalnum() and len(value) <= 8 else "mkv"


def _finding(code: str, severity: str, message: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message}


def _primary_files(items: list[MediaItem]) -> dict[Any, Any]:
    """The present primary version's file for each item."""

    files: dict[Any, Any] = {}
    for version in (
        MediaVersion.objects.filter(media_item__in=items, media_file__is_present=True)
        .select_related("media_file")
        .order_by("media_item_id", "-is_primary", "media_file__relative_path")
    ):
        files.setdefault(version.media_item_id, version.media_file)
    return files


def _selected_art(library, target_type: str, target_ids: list, types) -> dict[Any, list[ArtworkFile]]:
    art: dict[Any, list[ArtworkFile]] = defaultdict(list)
    for artwork in ArtworkFile.objects.filter(
        library=library, target_type=target_type, target_id__in=target_ids, is_selected=True, is_present=True
    ).order_by("artwork_type", "relative_path"):
        if artwork.artwork_type in types and not is_embedded_artwork_path(artwork.relative_path):
            art[artwork.target_id].append(artwork)
    return art


def _art_files(artworks: list[ArtworkFile], place, *, media_file, group: tuple[str, str]) -> list[Desired]:
    """Desired copies of selected artwork. ``place(artwork)`` gives its (folder, file stem)."""

    output = []
    for artwork in artworks:
        extension = _extension(artwork.extension or PurePosixPath(artwork.relative_path).suffix)
        folder, stem = place(artwork)
        output.append(
            Desired(
                path=f"{folder}/{stem}.{extension}" if folder else f"{stem}.{extension}",
                kind=Kind.ART,
                channel=None,
                media_file=media_file,
                source_path=artwork.relative_path,
                fingerprint=f"{artwork.relative_path}|{artwork.size_bytes}|{artwork.modified_ns}",
                group_id=group[0],
                group_title=group[1],
            )
        )
    return output


def _unique_ids(external_ids: dict, order=UNIQUE_IDS) -> list[tuple[str, Any, dict[str, str]]]:
    ids = {str(key).casefold(): str(value).strip() for key, value in (external_ids or {}).items() if str(value).strip()}
    output = []
    for index, name in enumerate(namespace for namespace in order if ids.get(namespace)):
        attributes = {"type": name}
        if index == 0:
            attributes["default"] = "true"
        output.append(("uniqueid", ids[name], attributes))
    return output


def _fields(values: dict[str, Any], order: list[str]) -> list[tuple[str, Any, dict[str, str]]]:
    fields: list[tuple[str, Any, dict[str, str]]] = []
    for tag in order:
        value = values.get(tag)
        for item in value if isinstance(value, list) else [value]:
            if item not in (None, ""):
                fields.append((tag, item, {}))
    return fields


def _runtime(media_file) -> str:
    seconds = getattr(media_file, "duration_seconds", None)
    return str(round(seconds / 60)) if seconds else ""


def movie_nfo(item: MediaItem, media_file) -> bytes:
    values = dict(catalog_values(Target("movie", item, item.library, item.title)))
    values["runtime"] = _runtime(media_file)
    order = ["title", "originaltitle", "sorttitle", "plot", "tagline", "mpaa", "premiered", "year", "runtime", "genre", "studio"]
    return _xml("movie", _fields(values, order) + _unique_ids(item.external_ids))


def show_nfo(series: Series) -> bytes:
    values = catalog_values(Target("series", series, series.library, series.title))
    order = ["title", "originaltitle", "sorttitle", "plot", "tagline", "mpaa", "year", "genre", "studio"]
    return _xml("tvshow", _fields(values, order) + _unique_ids(series.external_ids, TV_UNIQUE_IDS))


def episode_nfo(episode: Episode, media_file) -> bytes:
    values = dict(catalog_values(Target("episode", episode, episode.season.series.library, episode.media_item.title)))
    series = episode.season.series
    values["showtitle"] = series.title
    values["runtime"] = _runtime(media_file)
    # An episode without its own rating carries its show's, for parental controls.
    values["mpaa"] = values.get("mpaa") or series.content_rating
    order = ["title", "showtitle", "season", "episode", "aired", "plot", "runtime", "mpaa"]
    return _xml("episodedetails", _fields(values, order) + _unique_ids(episode.external_ids, TV_UNIQUE_IDS))


def _suffix(external_ids: dict, object_id) -> str:
    ids = {str(key).casefold(): str(value).strip() for key, value in (external_ids or {}).items()}
    for namespace in UNIQUE_IDS:
        if ids.get(namespace):
            return f"{namespace}-{safe_segment(ids[namespace], 24)}"
    return str(object_id)[:8]


def _folder_names(objects: list, title_year) -> dict[Any, str]:
    """A unique, safe folder name per object; collisions get a stable ID suffix."""

    names: dict[Any, str] = {}
    by_key: dict[str, list] = defaultdict(list)
    for obj in objects:
        title, year = title_year(obj)
        base = safe_segment(f"{title} ({year})" if year else title, MAX_NAME)
        names[obj.id] = base
        by_key[_key(base)].append(obj)
    for clashing in by_key.values():
        if len(clashing) < 2:
            continue
        for obj in clashing:
            suffix = f" [{_suffix(obj.external_ids, obj.id)}]"
            names[obj.id] = safe_segment(names[obj.id], MAX_NAME - len(suffix)) + suffix
    return names


def _check_paths(projection: Projection, desired: list[Desired], findings: list[dict[str, str]]) -> list[Desired]:
    """Drop files whose full path is too long or that still collide."""

    limit = MAX_PATH - len(projection.destination_path.rstrip("\\/")) - 1
    seen: dict[str, str] = {}
    too_long, collisions = 0, 0
    output = []
    for item in desired:
        if len(item.path) > limit:
            too_long += 1
            continue
        key = _key(item.path)
        if key in seen:
            collisions += 1
            continue
        seen[key] = item.path
        output.append(item)
    if too_long:
        findings.append(_finding("PATH_TOO_LONG", "warning", f"{too_long} file(s) skipped: their path would be too long for Windows."))
    if collisions:
        findings.append(_finding("PATH_COLLISION", "warning", f"{collisions} file(s) skipped: another file already uses the same name."))
    return output


# ---------------------------------------------------------------------------
# Movies
# ---------------------------------------------------------------------------


def _movie_year_value(item: MediaItem):
    year = _movie_year(item)
    if isinstance(year, int):
        return year
    return item.release_date.year if item.release_date else None


def _movies(projection: Projection, profile: profiles.Profile) -> tuple[list[Desired], list[dict[str, str]], dict[str, Any]]:
    library = projection.library
    items = list(MediaItem.objects.filter(library=library, media_type=MediaItem.MediaType.MOVIE).order_by("title", "id"))
    files = _primary_files(items)
    findings: list[dict[str, str]] = []
    missing = [item for item in items if item.id not in files]
    present = [item for item in items if item.id in files]
    if missing:
        findings.append(_finding("NO_FILE", "warning", f"{len(missing)} movie(s) skipped: no file in the library right now."))

    names = _folder_names(present, lambda item: (item.title or "Untitled", _movie_year_value(item)))
    art = _selected_art(library, ArtworkFile.TargetType.MEDIA_ITEM, [item.id for item in present], profile.art)
    desired: list[Desired] = []
    for item in present:
        media_file = files[item.id]
        folder = names[item.id]
        group = (str(item.id), item.title)
        extension = _extension(media_file.extension)
        common = {"channel": None, "media_file": media_file, "group_id": group[0], "group_title": group[1]}
        desired.append(Desired(path=f"{folder}/{folder}.{extension}", kind=Kind.VIDEO, **common))
        desired.append(Desired(path=f"{folder}/{folder}.nfo", kind=Kind.MOVIE_NFO, content=movie_nfo(item, media_file), **common))
        desired.extend(
            _art_files(
                art.get(item.id, []),
                lambda artwork, folder=folder: (folder, profile.movie_art(folder, artwork.artwork_type)),
                media_file=media_file,
                group=group,
            )
        )
    return desired, findings, {"movies": len(present), "skipped": len(missing)}


# ---------------------------------------------------------------------------
# TV
# ---------------------------------------------------------------------------


def _tv(projection: Projection, profile: profiles.Profile) -> tuple[list[Desired], list[dict[str, str]], dict[str, Any]]:
    library = projection.library
    episodes = list(
        Episode.objects.filter(season__series__library=library)
        .select_related("season", "season__series", "media_item")
        .order_by("season__series__title", "season__season_number", "episode_number", "id")
    )
    files = _primary_files([episode.media_item for episode in episodes])
    findings: list[dict[str, str]] = []
    multi = [e for e in episodes if e.episode_end_number and e.episode_end_number > e.episode_number]
    no_file = [e for e in episodes if e.media_item_id not in files]
    if multi:
        findings.append(
            _finding("MULTI_EPISODE", "warning", f"{len(multi)} multi-episode file(s) skipped: not supported in projections yet.")
        )
    if no_file:
        findings.append(_finding("NO_FILE", "warning", f"{len(no_file)} episode(s) skipped: no file in the library right now."))
    usable = [e for e in episodes if e not in multi and e.media_item_id in files]

    series_list = sorted({e.season.series for e in usable}, key=lambda value: (value.title.casefold(), str(value.id)))
    names = _folder_names(series_list, lambda series: (series.title or "Untitled", series.start_year))
    series_art = _selected_art(library, ArtworkFile.TargetType.SERIES, [s.id for s in series_list], profile.art)
    seasons = {e.season for e in usable}
    season_art = _selected_art(library, ArtworkFile.TargetType.SEASON, [s.id for s in seasons], profile.art)
    episode_thumbs = _selected_art(
        library, ArtworkFile.TargetType.EPISODE, [e.id for e in usable], {ArtworkFile.ArtworkType.PRIMARY, ArtworkFile.ArtworkType.THUMB}
    )

    desired: list[Desired] = []
    first_file: dict[Any, Any] = {}
    seen_numbers: set[tuple] = set()
    duplicates = 0
    for episode in usable:
        series = episode.season.series
        number = (series.id, episode.season.season_number, episode.episode_number)
        if number in seen_numbers:
            duplicates += 1
            continue
        seen_numbers.add(number)
        media_file = files[episode.media_item_id]
        first_file.setdefault(series.id, media_file)
        group = (str(series.id), series.title)
        show = names[series.id]
        season_folder = f"{show}/Season {episode.season.season_number:02d}"
        title = safe_segment(episode.media_item.title, MAX_EPISODE_TITLE) if episode.media_item.title else ""
        code = f"S{episode.season.season_number:02d}E{episode.episode_number:02d}"
        base = f"{season_folder}/{safe_segment(series.title, 60)} {code}" + (f" - {title}" if title else "")
        common = {"channel": None, "media_file": media_file, "group_id": group[0], "group_title": group[1]}
        desired.append(Desired(path=f"{base}.{_extension(media_file.extension)}", kind=Kind.VIDEO, **common))
        desired.append(Desired(path=f"{base}.nfo", kind=Kind.EPISODE_NFO, content=episode_nfo(episode, media_file), **common))
        stem = PurePosixPath(base).name
        desired.extend(
            _art_files(
                episode_thumbs.get(episode.id, [])[:1],
                lambda _artwork, folder=season_folder, stem=stem: (folder, f"{stem}-thumb"),
                media_file=media_file,
                group=group,
            )
        )
    if duplicates:
        findings.append(_finding("DUPLICATE_EPISODE", "warning", f"{duplicates} episode(s) skipped: another file has the same episode number."))

    seasons_done: set = set()
    for episode in usable:
        season = episode.season
        if season.id in seasons_done or season.series_id not in first_file:
            continue
        seasons_done.add(season.id)
        group = (str(season.series_id), season.series.title)
        show = names[season.series_id]
        desired.extend(
            _art_files(
                season_art.get(season.id, []),
                lambda artwork, show=show, season=season: profile.season_art(
                    show, f"{show}/Season {season.season_number:02d}", season.season_number, artwork.artwork_type
                ),
                media_file=first_file[season.series_id],
                group=group,
            )
        )
    for series in series_list:
        if series.id not in first_file:
            continue
        group = (str(series.id), series.title)
        common = {"channel": None, "media_file": first_file[series.id], "group_id": group[0], "group_title": group[1]}
        desired.append(Desired(path=f"{names[series.id]}/tvshow.nfo", kind=Kind.SHOW_NFO, content=show_nfo(series), **common))
        desired.extend(
            _art_files(
                series_art.get(series.id, []),
                lambda artwork, folder=names[series.id]: (folder, profile.art[artwork.artwork_type]),
                media_file=first_file[series.id],
                group=group,
            )
        )
    overview = {
        "series": [
            {"id": str(series.id), "title": series.title, "folder": names[series.id], "rating": series.content_rating}
            for series in series_list
        ],
        "skipped": len(multi) + len(no_file) + duplicates,
    }
    return desired, findings, overview


# ---------------------------------------------------------------------------
# Engine entry points
# ---------------------------------------------------------------------------


def plan(projection: Projection) -> dict[str, Any]:
    profile = profiles.for_target(projection.output_profile.target)
    if projection.layout == Projection.Layout.MOVIES:
        desired, findings, overview = _movies(projection, profile)
    else:
        desired, findings, overview = _tv(projection, profile)
    desired = _check_paths(projection, desired, findings)
    manifest = {row.relative_path: row for row in ProjectionFile.objects.filter(projection=projection)}
    actions = diff(desired, manifest)

    pending: dict[str, int] = defaultdict(int)
    for action in actions:
        if action.group_id:
            pending[action.group_id] += 1
    files: dict[str, int] = defaultdict(int)
    for item in desired:
        files[item.kind] += 1
    overview["files"] = dict(files)
    for row in overview.get("series", []):
        row["pending"] = pending.get(row["id"], 0)
        row["episodes"] = sum(1 for item in desired if item.kind == Kind.VIDEO and item.group_id == row["id"])
    return {"actions": actions, "desired": desired, "findings": findings, "overview": overview}


def filter_scope(actions: list, scope_id: str | None) -> list:
    if not scope_id:
        return actions
    return [action for action in actions if action.group_id == str(scope_id)]
