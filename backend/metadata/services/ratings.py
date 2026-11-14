"""Content-rating coverage and reviewed rating suggestions for a library.

Coverage is read-only. Suggestions search the library's metadata provider for
unrated movies and series and return what an apply *would* do, including the
preview fingerprints the existing apply endpoint requires. Nothing here writes
catalog data; each suggested rating is applied only when a person confirms it
through the normal, fully validated apply path.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db.models import Q
from django.shortcuts import get_object_or_404

from catalog.models import CanonicalFieldState, Series
from libraries.models import Library
from media.models import MediaItem
from metadata.providers.types import MetadataProviderError, MetadataTargetType
from metadata.services.matching import TIER_LIKELY, TIER_STRONG
from metadata.services.provider_match import (
    MatchRequestError,
    ResolvedTarget,
    _provider_for,
    build_preview,
    resolve_target,
    search_candidates,
)

# US rating systems. Jellyfin compares movie (MPA) and TV Parental Guidelines
# ratings on one scale, so both sets count as recognized for either kind.
US_MOVIE_RATINGS = ("G", "PG", "PG-13", "R", "NC-17")
US_TV_RATINGS = ("TV-Y", "TV-Y7", "TV-Y7-FV", "TV-G", "TV-PG", "TV-14", "TV-MA")
RECOGNIZED_RATINGS = frozenset(US_MOVIE_RATINGS + US_TV_RATINGS)

STATUS_RATED = "rated"
STATUS_MISSING = "missing"
STATUS_UNRECOGNIZED = "unrecognized"
STATUSES = (STATUS_RATED, STATUS_MISSING, STATUS_UNRECOGNIZED)

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
MAX_SUGGESTIONS = 10

_KIND_TARGETS = {
    MetadataTargetType.MOVIE.value: CanonicalFieldState.TargetType.MEDIA_ITEM,
    MetadataTargetType.SERIES.value: CanonicalFieldState.TargetType.SERIES,
}


def rating_status(value: str | None) -> str:
    rating = (value or "").strip()
    if not rating:
        return STATUS_MISSING
    return STATUS_RATED if rating.upper() in RECOGNIZED_RATINGS else STATUS_UNRECOGNIZED


def owned_library(*, user, library_id) -> Library:
    return get_object_or_404(Library, id=library_id, owner=user)


def _queryset(library: Library, kind: str):
    if kind == MetadataTargetType.MOVIE.value:
        return MediaItem.objects.filter(library=library, media_type=MediaItem.MediaType.MOVIE)
    if kind == MetadataTargetType.SERIES.value:
        return Series.objects.filter(library=library)
    raise MatchRequestError("Kind must be movie or series.")


def _recognized_q() -> Q:
    query = Q()
    for rating in RECOGNIZED_RATINGS:
        query |= Q(content_rating__iexact=rating)
    return query


def _status_filter(queryset, status: str):
    missing = Q(content_rating="")
    if status == STATUS_MISSING:
        return queryset.filter(missing)
    if status == STATUS_RATED:
        return queryset.filter(_recognized_q())
    if status == STATUS_UNRECOGNIZED:
        return queryset.exclude(missing).exclude(_recognized_q())
    return queryset


def _summary(library: Library) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {}
    for kind in _KIND_TARGETS:
        queryset = _queryset(library, kind)
        total = queryset.count()
        missing = _status_filter(queryset, STATUS_MISSING).count()
        rated = _status_filter(queryset, STATUS_RATED).count()
        output[kind] = {
            "total": total,
            STATUS_RATED: rated,
            STATUS_MISSING: missing,
            STATUS_UNRECOGNIZED: total - rated - missing,
        }
    return output


def _year(kind: str, obj) -> int | None:
    if kind == MetadataTargetType.SERIES.value:
        return obj.start_year
    year = ((obj.canonical_metadata or {}).get("semantic") or {}).get("year")
    if isinstance(year, int):
        return year
    return obj.release_date.year if obj.release_date else None


def _page_number(value: Any, name: str, default: int, maximum: int) -> int:
    if value in (None, ""):
        return default
    try:
        number = int(str(value))
    except ValueError as exc:
        raise MatchRequestError(f"{name} must be a whole number.") from exc
    if not 1 <= number <= maximum:
        raise MatchRequestError(f"{name} must be between 1 and {maximum}.")
    return number


def rating_coverage(
    library: Library,
    *,
    kind: str,
    status: str | None = None,
    search: str | None = None,
    page: Any = None,
    page_size: Any = None,
) -> dict[str, Any]:
    if status and status not in STATUSES and status != "all":
        raise MatchRequestError("Status must be rated, missing, unrecognized, or all.")
    page_number = _page_number(page, "Page", 1, 100_000)
    size = _page_number(page_size, "Page size", DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE)

    queryset = _status_filter(_queryset(library, kind), status or "all")
    if search and search.strip():
        queryset = queryset.filter(title__icontains=search.strip()[:200])
    queryset = queryset.order_by("title", "id")
    total = queryset.count()
    rows = list(queryset[(page_number - 1) * size : page_number * size])

    states = {
        state.target_id: state
        for state in CanonicalFieldState.objects.filter(
            target_type=_KIND_TARGETS[kind],
            target_id__in=[row.id for row in rows],
            field_name="content_rating",
        )
    }
    results = []
    for row in rows:
        state = states.get(row.id)
        results.append(
            {
                "kind": kind,
                "id": str(row.id),
                "title": row.title,
                "year": _year(kind, row),
                "content_rating": row.content_rating,
                "status": rating_status(row.content_rating),
                "source": state.source if state else None,
                "source_label": state.get_source_display() if state else None,
                "locked": bool(state and state.locked),
            }
        )

    return {
        "library_id": str(library.id),
        "kind": kind,
        "status": status or "all",
        "summary": _summary(library),
        "recognized_ratings": {"movie": list(US_MOVIE_RATINGS), "tv": list(US_TV_RATINGS)},
        "page": page_number,
        "page_size": size,
        "total": total,
        "next_page": page_number + 1 if page_number * size < total else None,
        "results": results,
    }


def _suggestion(resolved: ResolvedTarget, connection_id: str | None) -> dict[str, Any]:
    base = {
        "kind": resolved.kind.value,
        "id": str(resolved.obj.id),
        "title": resolved.current.get("title") or "",
        "year": resolved.match_target.year,
        "content_rating": resolved.current.get("content_rating") or "",
    }
    try:
        search = search_candidates(resolved, connection_id=connection_id, query=None, year=resolved.match_target.year)
        candidates = search["results"]
        if not candidates and resolved.match_target.year:
            # A wrong local year shouldn't hide the right title entirely.
            candidates = search_candidates(resolved, connection_id=connection_id, query=None)["results"]
    except MetadataProviderError as error:
        return {**base, "status": "error", "message": error.message}

    confident = next((item for item in candidates if item["match"]["tier"] in (TIER_STRONG, TIER_LIKELY)), None)
    if confident is None:
        return {
            **base,
            "status": "needs_review",
            "message": (
                "No confident match. Open the item's Match tab to choose one."
                if candidates
                else "No results. Open the item's Match tab to search with a different title."
            ),
            "candidate": candidates[0] if candidates else None,
        }

    try:
        preview = build_preview(resolved, connection_id=connection_id, source_id=confident["source_id"])
    except MetadataProviderError as error:
        return {**base, "status": "error", "message": error.message, "candidate": confident}

    row = next(item for item in preview["fields"] if item["field"] == "content_rating")
    result = {
        **base,
        "candidate": confident,
        "rating": row["proposed"],
        "territory": row["territory"],
        "options": row.get("options") or [],
        "note": row["note"],
    }
    if row["status"] == "missing":
        return {**result, "status": "no_rating", "message": row["note"] or "The provider has no rating for this title."}
    if row["status"] == "locked":
        return {**result, "status": "locked", "message": row["note"]}
    if row["status"] == "unchanged":
        return {**result, "status": "unchanged", "message": "Already has this rating."}

    return {
        **result,
        "status": "suggested",
        "message": "",
        # Everything the existing apply endpoint needs for this one field.
        "apply": {
            "connection": preview["connection"]["connection_id"],
            "source_id": preview["source_id"],
            "territory": preview["territory"],
            "fields": ["content_rating"],
            "target_revision": preview["target_revision"],
            "provider_snapshot": preview["provider_snapshot"],
        },
    }


def rating_suggestions(
    library: Library,
    *,
    user,
    kind: str,
    ids: list[str],
    connection_id: str | None = None,
) -> dict[str, Any]:
    if kind not in _KIND_TARGETS:
        raise MatchRequestError("Kind must be movie or series.")
    requested = [item.strip() for item in ids if item.strip()]
    if not requested:
        raise MatchRequestError("Choose at least one item.")
    unique_ids = list(dict.fromkeys(_valid_uuids(requested)))
    if len(unique_ids) != len(set(requested)):
        raise MatchRequestError("Item IDs must be valid IDs.")
    if len(unique_ids) > MAX_SUGGESTIONS:
        raise MatchRequestError(f"Ask for at most {MAX_SUGGESTIONS} suggestions at a time.")

    owned = {str(value) for value in _queryset(library, kind).filter(id__in=unique_ids).values_list("id", flat=True)}
    if any(item not in owned for item in unique_ids):
        raise MatchRequestError("Some items aren't in this library.", status=404)

    targets = [resolve_target(user=user, target_type=kind, target_id=item) for item in unique_ids]
    # Fail once, up front, if no provider connection can serve this library.
    connection, _provider = _provider_for(targets[0], connection_id)
    return {
        "library_id": str(library.id),
        "kind": kind,
        "connection": connection,
        "results": [_suggestion(target, connection["connection_id"]) for target in targets],
    }


def _valid_uuids(values: list[str]) -> list[str]:
    output = []
    for value in values:
        try:
            output.append(str(uuid.UUID(value)))
        except ValueError:
            continue
    return output
