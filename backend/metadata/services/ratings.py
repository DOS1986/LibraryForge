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

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404

from catalog.models import CanonicalFieldState, Channel, Series
from catalog.services.canonical import _record_manual_changes
from integrations.registry import get_provider_class
from libraries.models import Library
from media.models import MediaItem
from metadata.providers.types import (
    MetadataErrorCategory,
    MetadataProviderError,
    MetadataTargetType,
)
from metadata.services.matching import TIER_LIKELY, TIER_STRONG
from metadata.services.provider_match import (
    MatchRequestError,
    ResolvedTarget,
    _connection_rows,
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

KIND_MOVIE = MetadataTargetType.MOVIE.value
KIND_SERIES = MetadataTargetType.SERIES.value
KIND_CHANNEL = "channel"

_KIND_TARGETS = {
    KIND_MOVIE: CanonicalFieldState.TargetType.MEDIA_ITEM,
    KIND_SERIES: CanonicalFieldState.TargetType.SERIES,
    # Online-video channels are presented to media servers as TV series.
    KIND_CHANNEL: CanonicalFieldState.TargetType.CHANNEL,
}

KIND_INFO = {
    KIND_MOVIE: {"label": "Movies", "provider_suggestions": True, "nfo": True, "youtube_hints": False},
    KIND_SERIES: {"label": "TV series", "provider_suggestions": True, "nfo": True, "youtube_hints": False},
    # Channels get hints from YouTube's audience flags instead of provider matches.
    KIND_CHANNEL: {"label": "Online video channels", "provider_suggestions": False, "nfo": False, "youtube_hints": True},
}

# The kind a library shows first, by its content type.
_DEFAULT_KIND = {"movies": KIND_MOVIE, "tv": KIND_SERIES, "online_video": KIND_CHANNEL}

MAX_MANUAL_ITEMS = 500


def rating_status(value: str | None) -> str:
    rating = (value or "").strip()
    if not rating:
        return STATUS_MISSING
    return STATUS_RATED if rating.upper() in RECOGNIZED_RATINGS else STATUS_UNRECOGNIZED


def owned_library(*, user, library_id) -> Library:
    return get_object_or_404(Library, id=library_id, owner=user)


def _queryset(library: Library, kind: str):
    if kind == KIND_MOVIE:
        return MediaItem.objects.filter(library=library, media_type=MediaItem.MediaType.MOVIE)
    if kind == KIND_SERIES:
        return Series.objects.filter(library=library)
    if kind == KIND_CHANNEL:
        return Channel.objects.filter(library=library)
    raise MatchRequestError("Kind must be movie, series, or channel.")


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
    if kind == KIND_CHANNEL:
        return None
    if kind == KIND_SERIES:
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

    summary = _summary(library)
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
        "summary": summary,
        "recognized_ratings": {"movie": list(US_MOVIE_RATINGS), "tv": list(US_TV_RATINGS)},
        "kinds": available_kinds(library, summary),
        "page": page_number,
        "page_size": size,
        "total": total,
        "next_page": page_number + 1 if page_number * size < total else None,
        "results": results,
    }


def available_kinds(library: Library, summary: dict[str, dict[str, int]] | None = None) -> list[dict[str, Any]]:
    """Kinds this library actually contains, default first.

    A mixed library lists every kind it holds; an empty library still lists
    the kind its content type implies, so the tab isn't blank.
    """

    summary = summary or _summary(library)
    default = _DEFAULT_KIND.get(library.content_type)
    kinds = [kind for kind in _KIND_TARGETS if summary[kind]["total"] or kind == default]
    if not kinds:
        kinds = [KIND_MOVIE]
    kinds.sort(key=lambda kind: (kind != default, list(_KIND_TARGETS).index(kind)))
    return [{"kind": kind, "total": summary[kind]["total"], **KIND_INFO[kind]} for kind in kinds]


def set_ratings(library: Library, *, user, kind: str, ids: list[str], rating: Any) -> dict[str, Any]:
    """Set (or clear) the rating on chosen items by hand.

    Recorded like any manual edit: each changed field is locked with a manual
    source and gets a history entry, so scans, NFO imports, and provider
    suggestions won't replace it.
    """

    if kind not in _KIND_TARGETS:
        raise MatchRequestError("Kind must be movie, series, or channel.")
    if not isinstance(rating, str):
        raise MatchRequestError("Rating must be text.")
    value = " ".join(rating.split())
    if len(value) > 64:
        raise MatchRequestError("Ratings are at most 64 characters.")
    if value.upper() in RECOGNIZED_RATINGS:
        value = value.upper()

    requested = [str(item).strip() for item in ids if str(item).strip()]
    unique_ids = list(dict.fromkeys(_valid_uuids(requested)))
    if not unique_ids or len(unique_ids) != len(set(requested)):
        raise MatchRequestError("Choose items with valid IDs.")
    if len(unique_ids) > MAX_MANUAL_ITEMS:
        raise MatchRequestError(f"Set at most {MAX_MANUAL_ITEMS} ratings at a time.")

    target_type = _KIND_TARGETS[kind]
    changed = 0
    with transaction.atomic():
        objects = list(_queryset(library, kind).select_for_update().filter(id__in=unique_ids))
        if len(objects) != len(unique_ids):
            raise MatchRequestError("Some items aren't in this library.", status=404)
        for obj in objects:
            old = obj.content_rating or ""
            if old == value:
                continue
            obj.content_rating = value
            obj.save(update_fields=["content_rating", "updated_at"])
            _record_manual_changes(
                target_type=target_type,
                target_id=obj.id,
                changes={"content_rating": {"old": old, "new": value}},
                user=user,
                note="Rating cleared on the Ratings tab." if not value else "Rating set on the Ratings tab.",
            )
            changed += 1
    return {
        "library_id": str(library.id),
        "kind": kind,
        "rating": value,
        "requested": len(unique_ids),
        "changed": changed,
        "unchanged": len(unique_ids) - changed,
    }


def _known_ids(resolved: ResolvedTarget) -> dict[str, str]:
    return {
        str(key).casefold(): str(value).strip()
        for key, value in (resolved.current.get("external_ids") or {}).items()
        if str(value).strip()
    }


def _suggestion(
    resolved: ResolvedTarget,
    connection: dict[str, Any],
    known_ids: dict[str, str] | None = None,
) -> dict[str, Any]:
    """One provider's rating suggestion for one item.

    If the item (or an earlier provider's match) already has this provider's
    own ID, it is looked up directly instead of searched by title.
    """

    connection_id = connection["connection_id"]
    base = {
        "kind": resolved.kind.value,
        "id": str(resolved.obj.id),
        "title": resolved.current.get("title") or "",
        "year": resolved.match_target.year,
        "content_rating": resolved.current.get("content_rating") or "",
        "provider": connection["provider"],
        "provider_label": connection["provider_label"],
        "learned_ids": {},
    }
    namespace = connection.get("id_namespace") or ""
    direct_id = (known_ids or {}).get(namespace) if namespace else None

    if direct_id:
        try:
            preview = build_preview(resolved, connection_id=connection_id, source_id=direct_id)
        except MetadataProviderError as error:
            if error.category != MetadataErrorCategory.NOT_FOUND:
                return {**base, "status": "error", "message": error.message}
            preview = None
        if preview is not None:
            details = preview["provider_metadata"]
            candidate = {
                "provider": connection["provider"],
                "target_type": resolved.kind.value,
                "source_id": preview["source_id"],
                "title": details.get("title") or "",
                "year": details.get("year"),
                "match": {
                    "tier": TIER_STRONG,
                    "reasons": [
                        {
                            "code": "external_id_lookup",
                            "label": f"Looked up by its {namespace.upper()} ID",
                            "tone": "positive",
                        }
                    ],
                },
            }
            return _from_preview(base, candidate, preview)

    try:
        search = search_candidates(resolved, connection_id=connection_id, query=None, year=resolved.match_target.year)
        candidates = search["results"]
        if not candidates and resolved.match_target.year:
            # A wrong local year should not hide the right title entirely.
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
    return _from_preview(base, confident, preview)


def _from_preview(base: dict[str, Any], candidate: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
    row = next(item for item in preview["fields"] if item["field"] == "content_rating")
    learned = {
        item["namespace"]: item["value"]
        for item in preview["provider_metadata"].get("external_ids") or []
    }
    result = {
        **base,
        "learned_ids": learned,
        "candidate": candidate,
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

    estimated = bool(row.get("estimated"))
    return {
        **result,
        "status": "estimated" if estimated else "suggested",
        "message": row["note"] if estimated else "",
        "estimate": row.get("estimate"),
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


# When several providers are tried in turn, these outcomes end the chain;
# the rest let the next provider try, keeping the most useful fallback.
_FINAL_STATUSES = {"suggested", "unchanged", "locked"}
_FALLBACK_RANK = {"estimated": 0, "no_rating": 1, "needs_review": 2, "error": 3}


def _suggestion_chain(resolved: ResolvedTarget, connections: list[dict[str, Any]]) -> dict[str, Any]:
    """Try each provider in the library's priority order.

    A real rating from any provider wins. Otherwise the most useful fallback
    is kept: an estimate first, then "no rating", then "needs review". IDs a
    provider's match reveals (for example TMDB giving the IMDb ID) let later
    providers look the item up directly.
    """

    known = _known_ids(resolved)
    best = None
    tried = []
    for connection in connections:
        suggestion = _suggestion(resolved, connection, known)
        tried.append(connection["provider_label"])
        if suggestion["status"] in _FINAL_STATUSES:
            best = suggestion
            break
        for namespace, value in suggestion.get("learned_ids", {}).items():
            known.setdefault(namespace, value)
        if best is None or _FALLBACK_RANK.get(suggestion["status"], 9) < _FALLBACK_RANK.get(best["status"], 9):
            best = suggestion
    best = dict(best)
    best.pop("learned_ids", None)
    best["tried"] = tried
    return best


def rating_suggestions(
    library: Library,
    *,
    user,
    kind: str,
    ids: list[str],
    connection_id: str | None = None,
) -> dict[str, Any]:
    if kind not in (KIND_MOVIE, KIND_SERIES):
        raise MatchRequestError(
            "Provider rating suggestions are available for movies and TV series. "
            "Set online video channel ratings by hand."
        )
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
    if connection_id:
        # A specific provider was asked for: validate it and use only it.
        connections = [_provider_for(targets[0], connection_id)[0]]
    else:
        connections = [row for row, _link in _connection_rows(targets[0]) if row["available"]]
        if not connections:
            _provider_for(targets[0], None)  # raises the standard "no provider" error
    for connection in connections:
        connection["id_namespace"] = get_provider_class(connection["provider"]).definition.metadata_id_namespace
    return {
        "library_id": str(library.id),
        "kind": kind,
        "connection": connections[0],
        "connections": connections,
        "results": [_suggestion_chain(target, connections) for target in targets],
    }


def _valid_uuids(values: list[str]) -> list[str]:
    output = []
    for value in values:
        try:
            output.append(str(uuid.UUID(value)))
        except ValueError:
            continue
    return output
