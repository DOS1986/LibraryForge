"""Import content ratings from NFO files LibraryForge has already indexed.

This reads the ``<mpaa>`` value from each indexed movie NFO and ``tvshow.nfo``
(the stored, already-parsed data; no filesystem access), so it works for
read-only libraries. It never overwrites a rating that came from anywhere
else: manual edits, provider applies, and other locked values are kept, and a
different existing value is reported as a conflict rather than replaced. Only
empty ratings, or ratings previously imported from an NFO, are written.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import PurePosixPath
from typing import Any

from django.db import transaction

from catalog.models import CanonicalFieldState, MetadataChangeSet, Series
from catalog.services.canonical import set_field_provenance
from libraries.models import Library
from media.models import MediaFile, MediaItem
from metadata.models import NfoFile
from metadata.services.provider_match import MatchRequestError
from metadata.services.ratings import RECOGNIZED_RATINGS

MAX_RATING_LENGTH = 64
SAMPLE_LIMIT = 200

ACTION_SET = "set"
ACTION_UPDATE = "update"
ACTION_UNCHANGED = "unchanged"
ACTION_CONFLICT = "conflict"
ACTION_LOCKED = "locked"
ACTION_NFO_DISAGREE = "nfo_disagree"
ACTION_NO_RATING = "no_rating_in_nfo"
ACTION_NO_NFO = "no_nfo"

WRITE_ACTIONS = (ACTION_SET, ACTION_UPDATE)

_KINDS = {
    "movie": CanonicalFieldState.TargetType.MEDIA_ITEM,
    "series": CanonicalFieldState.TargetType.SERIES,
}
_RATED_PREFIX = re.compile(r"^rated\s+", re.IGNORECASE)
_COUNTRY_PREFIX = re.compile(r"^([A-Za-z]{2,3})\s*:\s*(.+)$")


def normalize_nfo_rating(value: Any) -> str:
    """Normalize common NFO certification spellings.

    Handles Kodi forms such as ``Rated PG-13``, ``US:R`` and
    ``US:PG-13 / UK:12A`` (first entry wins). Recognized US ratings are
    upper-cased; anything else is kept as written (trimmed), so values like
    ``Not Rated`` or ``15`` stay visible as unrecognized.
    """

    if isinstance(value, list):
        value = next((item for item in value if isinstance(item, str) and item.strip()), "")
    if not isinstance(value, str):
        return ""
    text = " ".join(value.split())
    text = text.split(" / ")[0].strip()
    text = _RATED_PREFIX.sub("", text)
    match = _COUNTRY_PREFIX.match(text)
    if match:
        text = _RATED_PREFIX.sub("", match.group(2).strip())
    if text.upper() in RECOGNIZED_RATINGS:
        return text.upper()
    return text if len(text) <= MAX_RATING_LENGTH else ""


def _nfo_rating(nfo: NfoFile) -> str:
    data = nfo.parsed_data or {}
    body = data.get(nfo.root_element) if isinstance(data, dict) else None
    if not isinstance(body, dict):
        return ""
    return normalize_nfo_rating(body.get("mpaa"))


def _same(left: str, right: str) -> bool:
    return (left or "").strip().casefold() == (right or "").strip().casefold()


def _movie_sources(library: Library) -> tuple[dict[Any, list[NfoFile]], list[MediaItem]]:
    items = list(
        MediaItem.objects.filter(library=library, media_type=MediaItem.MediaType.MOVIE).only(
            "id", "title", "content_rating"
        )
    )
    by_item: dict[Any, list[NfoFile]] = defaultdict(list)
    for nfo in NfoFile.objects.filter(
        library=library,
        is_present=True,
        parse_status=NfoFile.ParseStatus.OK,
        root_element="movie",
        media_item__media_type=MediaItem.MediaType.MOVIE,
    ).only("id", "media_item_id", "relative_path", "file_name", "root_element", "parsed_data"):
        by_item[nfo.media_item_id].append(nfo)
    return by_item, items


def _series_dir(paths: list[str], nfo_dirs: set[str]) -> str | None:
    """The folder holding this series' tvshow.nfo, chosen by its episodes' paths."""

    hits: Counter[str] = Counter()
    for path in paths:
        parent = PurePosixPath(path).parent
        for ancestor in [parent, *parent.parents]:
            key = str(ancestor).casefold()
            if key in nfo_dirs:
                hits[key] += 1
    if not hits:
        return None
    # Most episodes first, then the deepest folder.
    best, count = max(hits.items(), key=lambda item: (item[1], item[0].count("/")))
    return best if count * 2 >= len(paths) else None


def _series_sources(library: Library) -> tuple[dict[Any, list[NfoFile]], list[Series]]:
    items = list(Series.objects.filter(library=library).only("id", "title", "content_rating"))
    nfos = {
        str(PurePosixPath(nfo.relative_path).parent).casefold(): nfo
        for nfo in NfoFile.objects.filter(
            library=library,
            is_present=True,
            parse_status=NfoFile.ParseStatus.OK,
            root_element="tvshow",
        ).only("id", "relative_path", "file_name", "root_element", "parsed_data")
    }
    paths: dict[Any, list[str]] = defaultdict(list)
    for path, series_id in MediaFile.objects.filter(
        library=library,
        media_item__episode__season__series__library=library,
    ).values_list("relative_path", "media_item__episode__season__series_id"):
        paths[series_id].append(path)

    by_item: dict[Any, list[NfoFile]] = {}
    for series in items:
        folder = _series_dir(paths.get(series.id, []), set(nfos))
        if folder is not None:
            by_item[series.id] = [nfos[folder]]
    return by_item, items


def _plan(library: Library, kind: str) -> list[dict[str, Any]]:
    if kind not in _KINDS:
        raise MatchRequestError("Kind must be movie or series.")
    sources, items = _movie_sources(library) if kind == "movie" else _series_sources(library)
    states = {
        state.target_id: state
        for state in CanonicalFieldState.objects.filter(
            target_type=_KINDS[kind],
            target_id__in=[item.id for item in items],
            field_name="content_rating",
        )
    }

    rows: list[dict[str, Any]] = []
    for item in items:
        nfos = sources.get(item.id) or []
        current = item.content_rating or ""
        state = states.get(item.id)
        row: dict[str, Any] = {
            "kind": kind,
            "id": str(item.id),
            "title": item.title,
            "current": current,
            "current_source": state.source if state else None,
            "nfo_rating": "",
            "nfo_path": "",
        }
        if not nfos:
            rows.append({**row, "action": ACTION_NO_NFO})
            continue

        # Prefer "<movie file>.nfo" over a shared "movie.nfo".
        nfos = sorted(nfos, key=lambda nfo: (nfo.file_name.casefold() == "movie.nfo", nfo.relative_path))
        values = [(nfo, _nfo_rating(nfo)) for nfo in nfos]
        rated = [(nfo, value) for nfo, value in values if value]
        distinct = {value.casefold() for _nfo, value in rated}
        if not rated:
            rows.append({**row, "action": ACTION_NO_RATING, "nfo_path": nfos[0].relative_path})
            continue
        nfo, value = rated[0]
        row.update({"nfo_rating": value, "nfo_path": nfo.relative_path})
        if len(distinct) > 1:
            rows.append(
                {**row, "action": ACTION_NFO_DISAGREE, "other_values": sorted({v for _n, v in rated})}
            )
            continue

        from_nfo = bool(state and state.source == CanonicalFieldState.Source.NFO)
        if _same(current, value):
            action = ACTION_UNCHANGED
        elif state and state.locked:
            action = ACTION_LOCKED
        elif not current:
            action = ACTION_SET
        elif from_nfo:
            # The NFO is where this value came from, so follow its change.
            action = ACTION_UPDATE
        else:
            action = ACTION_CONFLICT
        rows.append({**row, "action": action})
    return rows


def _summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(row["action"] for row in rows)
    return {
        action: counts.get(action, 0)
        for action in (
            ACTION_SET,
            ACTION_UPDATE,
            ACTION_UNCHANGED,
            ACTION_CONFLICT,
            ACTION_LOCKED,
            ACTION_NFO_DISAGREE,
            ACTION_NO_RATING,
            ACTION_NO_NFO,
        )
    }


def preview_nfo_import(library: Library, *, kind: str) -> dict[str, Any]:
    rows = _plan(library, kind)
    interesting = [row for row in rows if row["action"] not in (ACTION_UNCHANGED, ACTION_NO_NFO, ACTION_NO_RATING)]
    order = {ACTION_CONFLICT: 0, ACTION_NFO_DISAGREE: 1, ACTION_LOCKED: 2, ACTION_UPDATE: 3, ACTION_SET: 4}
    interesting.sort(key=lambda row: (order.get(row["action"], 9), row["title"].casefold()))
    return {
        "library_id": str(library.id),
        "kind": kind,
        "total": len(rows),
        "summary": _summary(rows),
        "rows": interesting[:SAMPLE_LIMIT],
        "rows_truncated": len(interesting) > SAMPLE_LIMIT,
    }


def apply_nfo_import(library: Library, *, kind: str, user) -> dict[str, Any]:
    """Write NFO ratings for rows planned as set/update. Recomputed at apply
    time, so a value changed since the preview is never overwritten."""

    rows = [row for row in _plan(library, kind) if row["action"] in WRITE_ACTIONS]
    model = MediaItem if kind == "movie" else Series
    target_type = _KINDS[kind]
    with transaction.atomic():
        objects = {
            str(obj.id): obj
            for obj in model.objects.select_for_update().filter(id__in=[row["id"] for row in rows])
        }
        change_sets = []
        written = 0
        for row in rows:
            obj = objects.get(row["id"])
            if obj is None or not _same(obj.content_rating, row["current"]):
                continue
            obj.content_rating = row["nfo_rating"]
            obj.save(update_fields=["content_rating", "updated_at"])
            set_field_provenance(
                target_type=target_type,
                target_id=obj.id,
                field_name="content_rating",
                source=CanonicalFieldState.Source.NFO,
                value=row["nfo_rating"],
                source_ref=row["nfo_path"][:255],
            )
            change_sets.append(
                MetadataChangeSet(
                    target_type=target_type,
                    target_id=obj.id,
                    source=MetadataChangeSet.Source.SYSTEM,
                    source_ref=f"nfo:{row['nfo_path']}"[:255],
                    changes={"content_rating": {"old": row["current"], "new": row["nfo_rating"]}},
                    note=f"Imported rating from {row['nfo_path']}.",
                    changed_by=user,
                    details={"import": "nfo_rating", "nfo_path": row["nfo_path"]},
                )
            )
            written += 1
        MetadataChangeSet.objects.bulk_create(change_sets, batch_size=500)

    preview = preview_nfo_import(library, kind=kind)
    return {**preview, "written": written}
