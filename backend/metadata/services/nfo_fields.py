"""Write LibraryForge's metadata into NFO files, field by field.

LibraryForge's catalog is where metadata is edited (from embedded tags,
providers, or by hand). This keeps each item's NFO in step with it:

* **Existing NFOs** get only the chosen fields changed. Every other tag,
  comment, attribute, and the file's formatting and line endings are kept
  byte for byte. Fields are top-level tags of the NFO's root element, so
  nested tags with the same name (an actor's ``<name>``, a set's
  ``<overview>``) are never touched.
* **Missing NFOs** are created with every field LibraryForge has, beside the
  video (``<file name>.nfo`` for movies and episodes, ``tvshow.nfo`` in a
  series' folder), in the names Jellyfin reads.

The same safety rules as the other NFO writers apply: Read Only libraries
are never written; an NFO that changed on disk since the last scan isn't
overwritten (rescan first); a file that isn't indexed is never replaced;
every edited document is re-parsed and checked before it's written, through
the hardened NFO writer (library-root confinement, atomic replace).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from xml.sax.saxutils import escape

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from catalog.models import Episode, MediaVersion, Series
from catalog.services.artwork import _build_location_index
from catalog.services.canonical import _movie_year
from libraries.models import Library
from media.models import MediaItem
from metadata.models import NfoFile
from metadata.services import secure_nfo
from metadata.services.provider_match import MatchRequestError

SCALAR = "scalar"
LIST = "list"

ROOTS = {"movie": "movie", "series": "tvshow", "episode": "episodedetails"}

DEFAULT_BATCH = 50
MAX_BATCH = 200
SAMPLE_LIMIT = 200


@dataclass(frozen=True)
class Field:
    tag: str
    label: str
    kind: str = SCALAR


FIELDS = {
    "movie": (
        Field("title", "Title"),
        Field("originaltitle", "Original title"),
        Field("sorttitle", "Sort title"),
        Field("plot", "Plot"),
        Field("tagline", "Tagline"),
        Field("mpaa", "Rating"),
        Field("premiered", "Release date"),
        Field("year", "Year"),
        Field("genre", "Genres", LIST),
        Field("studio", "Studios", LIST),
    ),
    "series": (
        Field("title", "Title"),
        Field("originaltitle", "Original title"),
        Field("sorttitle", "Sort title"),
        Field("plot", "Plot"),
        Field("tagline", "Tagline"),
        Field("mpaa", "Rating"),
        Field("year", "First aired (year)"),
        Field("genre", "Genres", LIST),
        Field("studio", "Studios", LIST),
    ),
    "episode": (
        Field("title", "Title"),
        Field("plot", "Plot"),
        Field("season", "Season"),
        Field("episode", "Episode"),
        Field("aired", "Air date"),
        Field("mpaa", "Rating"),
    ),
}


# ---------------------------------------------------------------------------
# A tag-aware editor for NFO text
# ---------------------------------------------------------------------------

_MASK = re.compile(r"<!--.*?-->|<!\[CDATA\[.*?\]\]>|<\?.*?\?>|<!DOCTYPE[^>]*>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<(/?)([A-Za-z_][\w.:-]*)([^>]*?)(/?)>", re.DOTALL)


@dataclass
class _Child:
    name: str
    start: int
    end: int
    inner_start: int
    inner_end: int


def _masked(raw: str) -> str:
    # Blank out comments, CDATA, and processing instructions (keeping offsets)
    # so their contents are never mistaken for tags.
    return _MASK.sub(lambda match: " " * len(match.group(0)), raw)


def _children(raw: str, root: str) -> tuple[list[_Child], int]:
    """Direct children of the root element, and where the root closes."""

    text = _masked(raw)
    depth = 0
    open_child: tuple[str, int, int] | None = None
    children: list[_Child] = []
    root_close = -1
    for match in _TAG.finditer(text):
        closing, name, _attributes, self_closing = match.groups()
        if closing:
            depth -= 1
            if depth == 1 and open_child and name == open_child[0]:
                children.append(_Child(name, open_child[1], match.end(), open_child[2], match.start()))
                open_child = None
            elif depth == 0 and name.casefold() == root.casefold():
                root_close = match.start()
                break
            continue
        if depth == 0:
            if name.casefold() != root.casefold():
                raise ValueError(f"The NFO's root element isn't <{root}>.")
            if not self_closing:
                depth = 1
            continue
        if depth == 1:
            if self_closing:
                children.append(_Child(name, match.start(), match.end(), match.end(), match.end()))
                continue
            open_child = (name, match.start(), match.end())
        if not self_closing:
            depth += 1
    if root_close < 0:
        raise ValueError(f"The NFO has no closing </{root}> tag.")
    return children, root_close


def _newline(raw: str) -> str:
    return "\r\n" if "\r\n" in raw else "\n"


def _indent(raw: str) -> str:
    match = re.search(r"\n([ \t]+)<", raw)
    return match.group(1) if match else "  "


def _remove(raw: str, child: _Child) -> str:
    start, end = child.start, child.end
    line_start = raw.rfind("\n", 0, start) + 1
    line_end_index = raw.find("\n", end)
    line_end = len(raw) if line_end_index < 0 else line_end_index + 1
    # Remove the whole line when the element is alone on it.
    if raw[line_start:start].strip() == "" and raw[end:line_end].strip() == "":
        return raw[:line_start] + raw[line_end:]
    return raw[:start] + raw[end:]


def _insert(raw: str, at: int, elements: list[str]) -> str:
    if not elements:
        return raw
    newline, indent = _newline(raw), _indent(raw)
    line_start = raw.rfind("\n", 0, at) + 1
    if raw[line_start:at].strip() == "":
        block = "".join(f"{indent}{element}{newline}" for element in elements)
        return raw[:line_start] + block + raw[line_start:]
    return raw[:at] + "".join(elements) + raw[at:]


def _element(tag: str, value: str) -> str:
    return f"<{tag}>{escape(value)}</{tag}>"


def set_nfo_fields(raw: str, root: str, updates: dict[str, str | list[str]]) -> str:
    """Return ``raw`` with the given top-level tags set, changing nothing else.

    A string sets one tag (an empty string removes it); a list replaces every
    occurrence of the tag with one element per value, in place.
    """

    for tag, value in updates.items():
        children, root_close = _children(raw, root)
        existing = [child for child in children if child.name == tag]

        if isinstance(value, str) and value and existing:
            first = existing[0]
            # Keep one: Jellyfin reads the last of duplicate tags.
            for extra in reversed(existing[1:]):
                raw = _remove(raw, extra)
            if raw[first.start:first.end].endswith("/>"):
                raw = raw[:first.start] + _element(tag, value) + raw[first.end:]
            else:
                raw = raw[:first.inner_start] + escape(value) + raw[first.inner_end:]
            continue

        values = value if isinstance(value, list) else ([value] if value else [])
        if existing:
            first = existing[0]
            line_start = raw.rfind("\n", 0, first.start) + 1
            alone = raw[line_start:first.start].strip() == ""
            for child in reversed(existing):
                raw = _remove(raw, child)
            # Put the new elements where the first old one was.
            anchor = line_start if alone else first.start
        else:
            anchor = root_close
        raw = _insert(raw, anchor, [_element(tag, item) for item in values])
    return raw


def read_nfo_fields(raw: str, root: str) -> dict[str, list[str]]:
    """Top-level tag texts of an NFO (all occurrences), from a safe parse."""

    parsed = secure_nfo.parse_nfo_content(raw)
    if parsed["status"] != NfoFile.ParseStatus.OK or parsed["root_element"] != root:
        raise ValueError(parsed.get("error") or "The NFO couldn't be read.")
    body = (parsed.get("parsed_data") or {}).get(root)
    output: dict[str, list[str]] = {}
    if isinstance(body, dict):
        for key, value in body.items():
            items = value if isinstance(value, list) else [value]
            output[key] = [item.strip() for item in items if isinstance(item, str)]
    return output


def build_nfo(root: str, values: dict[str, str | list[str]]) -> str:
    element = ET.Element(root)
    for tag, value in values.items():
        for item in value if isinstance(value, list) else [value]:
            if item:
                ET.SubElement(element, tag).text = item
    ET.indent(element, space="  ")
    return '<?xml version="1.0" encoding="utf-8" standalone="yes"?>\n' + ET.tostring(element, encoding="unicode") + "\n"


# ---------------------------------------------------------------------------
# Items and their NFOs
# ---------------------------------------------------------------------------


@dataclass
class Target:
    kind: str
    obj: Any
    library: Library
    title: str


def resolve(*, user, kind: str, item_id) -> Target:
    if kind == "movie":
        item = get_object_or_404(MediaItem, id=item_id, library__owner=user, media_type=MediaItem.MediaType.MOVIE)
        return Target(kind, item, item.library, item.title)
    if kind == "series":
        series = get_object_or_404(Series, id=item_id, library__owner=user)
        return Target(kind, series, series.library, series.title)
    if kind == "episode":
        episode = get_object_or_404(
            Episode.objects.select_related("season", "season__series", "media_item"),
            id=item_id,
            season__series__library__owner=user,
        )
        return Target(kind, episode, episode.season.series.library, episode.media_item.title)
    raise MatchRequestError("Kind must be movie, series, or episode.")


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()) if not isinstance(value, str) else value.strip()


def catalog_values(target: Target) -> dict[str, str | list[str]]:
    obj = target.obj
    if target.kind == "movie":
        year = _movie_year(obj) or (obj.release_date.year if obj.release_date else None)
        return {
            "title": _text(obj.title),
            "originaltitle": _text(obj.original_title),
            "sorttitle": _text(obj.sort_title),
            "plot": _text(obj.description),
            "tagline": _text(obj.tagline),
            "mpaa": _text(obj.content_rating),
            "premiered": obj.release_date.isoformat() if obj.release_date else "",
            "year": str(year) if year else "",
            "genre": [_text(value) for value in obj.genres or [] if _text(value)],
            "studio": [_text(value) for value in obj.studios or [] if _text(value)],
        }
    if target.kind == "series":
        return {
            "title": _text(obj.title),
            "originaltitle": _text(obj.original_title),
            "sorttitle": _text(obj.sort_title),
            "plot": _text(obj.description),
            "tagline": _text(obj.tagline),
            "mpaa": _text(obj.content_rating),
            "year": str(obj.start_year) if obj.start_year else "",
            "genre": [_text(value) for value in obj.genres or [] if _text(value)],
            "studio": [_text(value) for value in obj.studios or [] if _text(value)],
        }
    item = obj.media_item
    return {
        "title": _text(item.title),
        "plot": _text(item.description),
        "season": str(obj.season.season_number),
        "episode": str(obj.episode_number),
        "aired": obj.air_date.isoformat() if obj.air_date else "",
        "mpaa": _text(item.content_rating),
    }


def _primary_file(media_item: MediaItem):
    version = (
        MediaVersion.objects.filter(media_item=media_item, media_file__is_present=True)
        .select_related("media_file")
        .order_by("-is_primary", "media_file__relative_path")
        .first()
    )
    return version.media_file if version else None


def _series_folder(target: Target, index=None) -> str | None:
    index = index if index is not None else _build_location_index(target.library)
    folders = [folder for folder, series_id in index["series_dirs"].items() if series_id == target.obj.id]
    return folders[0] if len(folders) == 1 else None


def _existing_nfo(target: Target, planned: str | None) -> NfoFile | None:
    root = ROOTS[target.kind]
    queryset = NfoFile.objects.filter(library=target.library, is_present=True)
    if target.kind == "movie":
        found = queryset.filter(media_item=target.obj, root_element=root).order_by("relative_path").first()
    elif target.kind == "episode":
        found = queryset.filter(media_item=target.obj.media_item, root_element=root).order_by("relative_path").first()
    else:
        from metadata.services.nfo_ratings import _series_sources

        found = (_series_sources(target.library)[0].get(target.obj.id) or [None])[0]
    if found is None and planned:
        found = next((nfo for nfo in queryset.filter(file_name__iexact=PurePosixPath(planned).name)
                      if nfo.relative_path.casefold() == planned.casefold()), None)
    return found


def _planned_path(target: Target, index=None) -> tuple[str | None, Any, str]:
    """(relative path for a new NFO, its media file, problem)."""

    if target.kind == "series":
        folder = _series_folder(target, index)
        if folder is None:
            return None, None, "LibraryForge couldn't find this series' own folder. Rescan the library first."
        return ("tvshow.nfo" if folder in ("", ".") else f"{folder}/tvshow.nfo"), None, ""
    media_item = target.obj if target.kind == "movie" else target.obj.media_item
    media_file = _primary_file(media_item)
    if media_file is None:
        return None, None, "This item has no file in the library right now."
    path = PurePosixPath(media_file.relative_path.replace("\\", "/"))
    return path.with_suffix(".nfo").as_posix(), media_file, ""


def _status(ours: str | list[str], theirs: list[str] | None, field: Field) -> str:
    if theirs is None or not any(theirs):
        return "empty" if not ours else "missing"
    if not ours:
        # LibraryForge has nothing here; writing would erase the NFO's value.
        return "nfo_only"
    if field.kind == LIST:
        same = [value.casefold() for value in ours] == [value.casefold() for value in theirs]
    else:
        same = _text(ours).casefold() == _text(theirs[-1]).casefold()
    return "same" if same else "different"


def _display(value: list[str] | None, field: Field):
    if value is None:
        return None
    return value if field.kind == LIST else (value[-1] if value else "")


def nfo_comparison(target: Target) -> dict[str, Any]:
    library = target.library
    writable = library.management_mode != Library.ManagementMode.READ_ONLY
    planned, _media_file, problem = _planned_path(target)
    nfo = _existing_nfo(target, planned)
    current: dict[str, list[str]] | None = None
    if nfo is not None:
        if nfo.parse_status == NfoFile.ParseStatus.OK and nfo.root_element == ROOTS[target.kind]:
            try:
                current = read_nfo_fields(nfo.raw_xml, ROOTS[target.kind])
            except ValueError as error:
                problem = str(error)
        else:
            problem = "The NFO couldn't be parsed. Fix it with the raw editor on the NFO page first."
    values = catalog_values(target)
    fields = []
    for field in FIELDS[target.kind]:
        theirs = None if current is None else current.get(field.tag)
        fields.append(
            {
                "tag": field.tag,
                "label": field.label,
                "list": field.kind == LIST,
                "libraryforge": values[field.tag],
                "nfo": _display(theirs, field) if current is not None else None,
                "status": _status(values[field.tag], theirs if current is not None else None, field)
                if current is not None
                else ("missing" if values[field.tag] else "empty"),
            }
        )
    return {
        "kind": target.kind,
        "id": str(target.obj.id),
        "title": target.title,
        "nfo": {
            "exists": nfo is not None,
            "id": str(nfo.id) if nfo else None,
            "path": nfo.relative_path if nfo else planned,
            "root_element": ROOTS[target.kind],
        },
        "problem": problem or None,
        "writable": writable,
        "root_error": secure_nfo.library_root_error(library) if writable else None,
        "fields": fields,
    }


def _check_writable(library: Library) -> None:
    if library.management_mode == Library.ManagementMode.READ_ONLY:
        raise MatchRequestError(
            "This library is Read Only, so LibraryForge can't change its NFO files. "
            "Change its management mode to Sidecar Only to allow it.",
            status=409,
        )
    root_error = secure_nfo.library_root_error(library)
    if root_error:
        raise MatchRequestError(root_error, status=409)


def _read_current(nfo: NfoFile) -> str | None:
    path = secure_nfo._destination_for(nfo)
    if path.stat().st_size > secure_nfo._max_nfo_bytes() or not nfo.raw_xml:
        return None
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        current = handle.read()
    normalize = lambda text: text.replace("\r\n", "\n").replace("\r", "\n")
    return current if normalize(current) == normalize(nfo.raw_xml) else None


def _verify(raw: str, root: str, expected: dict[str, str | list[str]]) -> None:
    read = read_nfo_fields(raw, root)
    for tag, value in expected.items():
        got = read.get(tag, [])
        if isinstance(value, list):
            ok = [item.casefold() for item in got] == [item.casefold() for item in value]
        else:
            ok = (_text(got[-1]) if got else "").casefold() == _text(value).casefold()
        if not ok:
            raise ValueError(f"The edited NFO didn't read back <{tag}> correctly, so it wasn't written.")


def write_fields(target: Target, *, tags: list[str] | None) -> dict[str, Any]:
    """Update chosen fields in the existing NFO, or create the NFO if missing.

    ``tags`` None means every field that differs (or, for a new NFO, every
    field LibraryForge has).
    """

    library = target.library
    _check_writable(library)
    root = ROOTS[target.kind]
    known = {field.tag for field in FIELDS[target.kind]}
    if tags is not None:
        unknown = sorted(set(tags) - known)
        if unknown:
            raise MatchRequestError(f"Unknown NFO fields: {', '.join(unknown)}.")
    values = catalog_values(target)
    planned, media_file, problem = _planned_path(target)
    nfo = _existing_nfo(target, planned)

    if nfo is None:
        if not planned:
            raise MatchRequestError(problem, status=409)
        return _create(target, planned, media_file, values, root)

    if nfo.parse_status != NfoFile.ParseStatus.OK or nfo.root_element != root:
        raise MatchRequestError("The NFO couldn't be parsed. Fix it with the raw editor on the NFO page first.", status=409)
    comparison = {row["tag"]: row for row in nfo_comparison(target)["fields"]}
    chosen = tags if tags is not None else list(comparison)
    # Only fields LibraryForge has a different value for; an NFO value is never erased.
    updates = {tag: values[tag] for tag in chosen if comparison[tag]["status"] in ("different", "missing")}
    if not updates:
        return {"result": "unchanged", "path": nfo.relative_path, "written": []}
    try:
        current = _read_current(nfo)
    except OSError as error:
        raise MatchRequestError(str(error) or "The NFO couldn't be read.", status=409) from error
    if current is None:
        raise MatchRequestError("The NFO changed since the last scan. Rescan the library, then try again.", status=409)
    try:
        updated = set_nfo_fields(current, root, updates)
        _verify(updated, root, updates)
        secure_nfo.write_nfo_file(nfo, updated)
    except (ValueError, PermissionError, OSError) as error:
        raise MatchRequestError(str(error) or "The NFO couldn't be written.", status=409) from error
    return {"result": "updated", "path": nfo.relative_path, "written": sorted(updates)}


def _create(target: Target, relative: str, media_file, values: dict[str, Any], root: str) -> dict[str, Any]:
    library = target.library
    probe = NfoFile(library=library, relative_path=relative, file_name=PurePosixPath(relative).name)
    try:
        destination = secure_nfo._destination_for(probe)
    except PermissionError as error:
        raise MatchRequestError(str(error), status=409) from error
    if destination.exists():
        raise MatchRequestError(
            f"{PurePosixPath(relative).name} already exists but isn't indexed yet. Rescan the library first.", status=409
        )
    raw = build_nfo(root, values)
    _verify(raw, root, {tag: value for tag, value in values.items() if value})
    with transaction.atomic():
        nfo = NfoFile.objects.create(
            library=library,
            media_item=target.obj if target.kind == "movie" else (target.obj.media_item if target.kind == "episode" else None),
            media_file=media_file,
            relative_path=relative,
            file_name=PurePosixPath(relative).name,
            is_generated=True,
            last_seen_at=timezone.now(),
        )
        try:
            secure_nfo.write_nfo_file(nfo, raw)
        except (ValueError, PermissionError, OSError) as error:
            raise MatchRequestError(str(error) or "The NFO couldn't be written.", status=409) from error
    return {"result": "created", "path": relative, "written": sorted(tag for tag, value in values.items() if value)}


# ---------------------------------------------------------------------------
# Creating missing NFOs for a whole library
# ---------------------------------------------------------------------------


def _missing(library: Library, kind: str) -> list[dict[str, Any]]:
    if kind == "movie":
        items = list(MediaItem.objects.filter(library=library, media_type=MediaItem.MediaType.MOVIE).order_by("title", "id"))
        with_nfo = set(
            NfoFile.objects.filter(library=library, is_present=True, root_element="movie").values_list("media_item_id", flat=True)
        )
        index = None
    elif kind == "series":
        from metadata.services.nfo_ratings import _series_sources

        items = list(Series.objects.filter(library=library).order_by("title", "id"))
        with_nfo = set(_series_sources(library)[0])
        index = _build_location_index(library)
        tvshow = {
            str(PurePosixPath(path).parent).casefold()
            for path in NfoFile.objects.filter(library=library, is_present=True, root_element="tvshow").values_list(
                "relative_path", flat=True
            )
        }
    else:
        raise MatchRequestError("Kind must be movie or series.")

    rows = []
    for item in items:
        if item.id in with_nfo:
            continue
        target = Target(kind, item, library, item.title)
        planned, _media_file, problem = _planned_path(target, index)
        if kind == "series" and planned and str(PurePosixPath(planned).parent).casefold() in tvshow:
            continue
        rows.append({"id": str(item.id), "title": item.title, "path": planned or "", "problem": problem or ""})
    return rows


def preview_missing_nfos(library: Library, *, kind: str) -> dict[str, Any]:
    rows = _missing(library, kind)
    ready = [row for row in rows if row["path"]]
    writable = library.management_mode != Library.ManagementMode.READ_ONLY
    return {
        "library_id": str(library.id),
        "kind": kind,
        "writable": writable,
        "root_error": secure_nfo.library_root_error(library) if writable and ready else None,
        "missing": len(rows),
        "ready": len(ready),
        "blocked": len(rows) - len(ready),
        "rows": rows[:SAMPLE_LIMIT],
        "rows_truncated": len(rows) > SAMPLE_LIMIT,
    }


def create_missing_nfos(library: Library, *, kind: str, cursor: str | None = None, batch: Any = None) -> dict[str, Any]:
    _check_writable(library)
    try:
        size = int(batch) if batch not in (None, "") else DEFAULT_BATCH
    except (TypeError, ValueError) as exc:
        raise MatchRequestError("Batch must be a whole number.") from exc
    if not 1 <= size <= MAX_BATCH:
        raise MatchRequestError(f"Batch must be between 1 and {MAX_BATCH}.")

    key = lambda row: f"{row['title'].casefold()}\x00{row['id']}"
    pending = sorted((row for row in _missing(library, kind) if row["path"]), key=key)
    if cursor:
        pending = [row for row in pending if key(row) > cursor]
    selected = pending[:size]
    model = MediaItem if kind == "movie" else Series
    objects = {str(obj.id): obj for obj in model.objects.filter(id__in=[row["id"] for row in selected])}

    created, problems = 0, []
    for row in selected:
        obj = objects.get(row["id"])
        if obj is None:
            continue
        try:
            write_fields(Target(kind, obj, library, obj.title), tags=None)
            created += 1
        except MatchRequestError as error:
            problems.append({"title": row["title"], "path": row["path"], "message": error.message})
    remaining = len(pending) - len(selected)
    return {
        "library_id": str(library.id),
        "kind": kind,
        "created": created,
        "problems": problems,
        "next_cursor": key(selected[-1]) if selected and remaining > 0 else None,
        "remaining": remaining,
    }
