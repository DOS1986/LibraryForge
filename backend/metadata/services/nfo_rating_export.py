"""Write LibraryForge content ratings into existing NFO files.

Media servers such as Jellyfin read a title's rating from ``<mpaa>`` in its
NFO file. This writes the catalog rating into the movie NFOs and
``tvshow.nfo`` files LibraryForge has already indexed, so a media server's
parental controls see the ratings set here.

Safety rules:

* Only libraries that allow sidecar changes (Full Control or Sidecar Only)
  are written; read-only libraries can still be previewed.
* Only existing, successfully parsed XML NFOs are changed. No NFO is created.
* Only the ``<mpaa>`` value changes. The rest of the file is kept as is,
  including formatting, comments, other tags, and line endings. A missing
  ``<mpaa>`` is added just before the closing root tag.
* A file whose size or modification time differs from the last scan is
  skipped, so changes made by other tools are never overwritten.
* Every edited document is re-parsed and checked before it is written, and
  writes go through the hardened NFO writer (library-root confinement,
  symlink checks, atomic replace).
"""

from __future__ import annotations

import re
from typing import Any
from xml.sax.saxutils import escape

from libraries.models import Library
from metadata.models import NfoFile
from metadata.services import secure_nfo
from metadata.services.nfo_ratings import (
    _movie_sources,
    _nfo_rating,
    _series_sources,
    normalize_nfo_rating,
)
from metadata.services.provider_match import MatchRequestError

DEFAULT_BATCH = 100
MAX_BATCH = 500
SAMPLE_LIMIT = 200

ACTION_WRITE = "write"
ACTION_ADD = "add"
ACTION_UNCHANGED = "unchanged"
ACTION_NO_NFO = "no_nfo"
ACTION_UNRATED = "unrated"

WRITE_ACTIONS = (ACTION_WRITE, ACTION_ADD)

RESULT_WRITTEN = "written"
RESULT_CHANGED_ON_DISK = "changed_on_disk"
RESULT_FAILED = "failed"

_MPAA = re.compile(r"(<mpaa(?:\s[^>]*)?>)(.*?)(</mpaa\s*>)", re.IGNORECASE | re.DOTALL)
_EMPTY_MPAA = re.compile(r"<mpaa(?:\s[^>]*)?/>", re.IGNORECASE)


def writable(library: Library) -> bool:
    return library.management_mode != Library.ManagementMode.READ_ONLY


def set_mpaa(raw_xml: str, root_element: str, rating: str) -> str:
    """Return ``raw_xml`` with its ``<mpaa>`` set to ``rating``, changing nothing else."""

    value = escape(rating)
    if _MPAA.search(raw_xml):
        return _MPAA.sub(lambda match: f"{match.group(1)}{value}{match.group(3)}", raw_xml)
    if _EMPTY_MPAA.search(raw_xml):
        return _EMPTY_MPAA.sub(f"<mpaa>{value}</mpaa>", raw_xml)

    closing = re.compile(rf"</{re.escape(root_element)}\s*>", re.IGNORECASE)
    matches = list(closing.finditer(raw_xml))
    if not matches:
        raise ValueError(f"The NFO has no closing </{root_element}> tag.")
    position = matches[-1].start()
    newline = "\r\n" if "\r\n" in raw_xml else "\n"
    indent_match = re.search(r"\n([ \t]+)<", raw_xml)
    indent = indent_match.group(1) if indent_match else "  "
    line_start = raw_xml.rfind("\n", 0, position) + 1
    if raw_xml[line_start:position].strip() == "":
        # The closing tag is on its own line: add a properly indented line.
        return f"{raw_xml[:line_start]}{indent}<mpaa>{value}</mpaa>{newline}{raw_xml[line_start:]}"
    return f"{raw_xml[:position]}<mpaa>{value}</mpaa>{raw_xml[position:]}"


def _plan(library: Library, kind: str) -> list[dict[str, Any]]:
    if kind == "movie":
        sources, items = _movie_sources(library)
    elif kind == "series":
        sources, items = _series_sources(library)
    else:
        raise MatchRequestError("Kind must be movie or series.")

    rows: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda obj: (obj.title.casefold(), str(obj.id))):
        rating = normalize_nfo_rating(item.content_rating) or (item.content_rating or "").strip()
        base = {"kind": kind, "id": str(item.id), "title": item.title, "rating": rating}
        nfos = [
            nfo
            for nfo in sources.get(item.id) or []
            if nfo.parse_status == NfoFile.ParseStatus.OK and nfo.root_element in ("movie", "tvshow")
        ]
        if not rating:
            rows.append({**base, "action": ACTION_UNRATED, "nfo_path": "", "nfo_id": None, "nfo_rating": ""})
            continue
        if not nfos:
            rows.append({**base, "action": ACTION_NO_NFO, "nfo_path": "", "nfo_id": None, "nfo_rating": ""})
            continue
        for nfo in sorted(nfos, key=lambda value: value.relative_path):
            current = _nfo_rating(nfo)
            if current and current.casefold() == rating.casefold():
                action = ACTION_UNCHANGED
            elif current:
                action = ACTION_WRITE
            else:
                action = ACTION_ADD
            rows.append(
                {
                    **base,
                    "action": action,
                    "nfo_path": nfo.relative_path,
                    "nfo_id": str(nfo.id),
                    "nfo_rating": current,
                }
            )
    return rows


def _cursor(row: dict[str, Any]) -> str:
    return f"{row['title'].casefold()}\x00{row['id']}\x00{row['nfo_path']}"


def _summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {
        ACTION_WRITE: 0,
        ACTION_ADD: 0,
        ACTION_UNCHANGED: 0,
        ACTION_NO_NFO: 0,
        ACTION_UNRATED: 0,
    }
    for row in rows:
        counts[row["action"]] += 1
    return counts


def preview_nfo_export(library: Library, *, kind: str) -> dict[str, Any]:
    rows = _plan(library, kind)
    changes = [row for row in rows if row["action"] in WRITE_ACTIONS]
    return {
        "library_id": str(library.id),
        "kind": kind,
        "writable": writable(library),
        "management_mode": library.management_mode,
        "summary": _summary(rows),
        "files_to_write": len(changes),
        "rows": [{key: value for key, value in row.items() if key != "nfo_id"} for row in changes[:SAMPLE_LIMIT]],
        "rows_truncated": len(changes) > SAMPLE_LIMIT,
    }


def _normalized(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _read_current(nfo: NfoFile) -> str | None:
    """Fresh file contents, or None if the content changed since it was indexed.

    Content is compared rather than size and timestamp: media servers often
    re-save NFOs without changing them, which only moves the timestamp. A
    file whose content differs from the indexed copy is never overwritten.
    """

    path = secure_nfo._destination_for(nfo)
    if path.stat().st_size > secure_nfo._max_nfo_bytes() or not nfo.raw_xml:
        return None
    # newline="" keeps the file's own line endings intact for writing.
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        current = handle.read()
    return current if _normalized(current) == _normalized(nfo.raw_xml) else None


def _write_one(nfo: NfoFile, rating: str) -> tuple[str, str]:
    try:
        current = _read_current(nfo)
    except (OSError, PermissionError) as error:
        return RESULT_FAILED, str(error) or "The file could not be read."
    if current is None:
        return RESULT_CHANGED_ON_DISK, "The file changed since the last scan. Rescan the library first."

    try:
        updated = set_mpaa(current, nfo.root_element, rating)
        parsed = secure_nfo.parse_nfo_content(updated)
        body = (parsed.get("parsed_data") or {}).get(nfo.root_element)
        if (
            parsed["status"] != NfoFile.ParseStatus.OK
            or parsed["root_element"] != nfo.root_element
            or not isinstance(body, dict)
            or normalize_nfo_rating(body.get("mpaa")).casefold() != rating.casefold()
        ):
            return RESULT_FAILED, "The edited NFO didn't validate, so it was not written."
        secure_nfo.write_nfo_file(nfo, updated)
    except (OSError, PermissionError, ValueError) as error:
        return RESULT_FAILED, str(error) or "The file could not be written."
    return RESULT_WRITTEN, ""


def apply_nfo_export(
    library: Library,
    *,
    kind: str,
    cursor: str | None = None,
    batch: Any = None,
) -> dict[str, Any]:
    """Write one batch of NFO changes, in a stable order, starting after ``cursor``."""

    if not writable(library):
        raise MatchRequestError(
            "This library is Read Only, so LibraryForge can't change its NFO files. "
            "Change its management mode to Sidecar Only to allow it.",
            status=409,
        )
    try:
        size = int(batch) if batch not in (None, "") else DEFAULT_BATCH
    except (TypeError, ValueError) as exc:
        raise MatchRequestError("Batch must be a whole number.") from exc
    if not 1 <= size <= MAX_BATCH:
        raise MatchRequestError(f"Batch must be between 1 and {MAX_BATCH}.")

    pending = [row for row in _plan(library, kind) if row["action"] in WRITE_ACTIONS]
    if cursor:
        pending = [row for row in pending if _cursor(row) > cursor]
    selected = pending[:size]

    nfos = {
        str(nfo.id): nfo
        for nfo in NfoFile.objects.select_related("library").filter(
            library=library, id__in=[row["nfo_id"] for row in selected]
        )
    }
    results = []
    for row in selected:
        nfo = nfos.get(row["nfo_id"])
        if nfo is None:
            outcome, message = RESULT_FAILED, "The NFO record no longer exists."
        else:
            outcome, message = _write_one(nfo, row["rating"])
        results.append(
            {
                "title": row["title"],
                "nfo_path": row["nfo_path"],
                "rating": row["rating"],
                "previous": row["nfo_rating"],
                "result": outcome,
                "message": message,
            }
        )

    counts = {key: 0 for key in (RESULT_WRITTEN, RESULT_CHANGED_ON_DISK, RESULT_FAILED)}
    for result in results:
        counts[result["result"]] += 1
    remaining = len(pending) - len(selected)
    return {
        "library_id": str(library.id),
        "kind": kind,
        "counts": counts,
        # Only problems are listed individually; successful writes are counted.
        "problems": [result for result in results if result["result"] != RESULT_WRITTEN],
        "next_cursor": _cursor(selected[-1]) if selected and remaining > 0 else None,
        "remaining": remaining,
    }

