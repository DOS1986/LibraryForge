"""Read-only metadata-provider matching: target context, search, and preview.

Nothing in this module writes catalog data, field provenance, or change
history. It resolves an owned movie or series, picks an eligible provider
connection, retrieves normalized provider data, and describes what *could*
change. Applying a reviewed preview is a separate, later operation.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from django.shortcuts import get_object_or_404

from catalog.models import CanonicalFieldState, Series
from integrations.providers.base import provider_supports_metadata_target
from integrations.registry import get_provider_class
from integrations.services import active_links_for_library, provider_for_connection
from media.models import MediaItem
from metadata.providers.types import (
    MetadataErrorCategory,
    MetadataProviderError,
    MetadataTargetType,
    ProviderMetadata,
)
from metadata.services.matching import MatchTarget, match_hint
from metadata.services.rating_equivalents import estimate_us_rating

SEARCH_PAGE_SIZE = 20
DEFAULT_TERRITORY = "US"
_TERRITORY_PATTERN = re.compile(r"^[A-Z]{2}$")
_NAMESPACE_LABELS = {"imdb": "IMDb ID", "tmdb": "TMDB ID", "tvdb": "TVDB ID", "wikidata": "Wikidata ID"}

STATUS_UNCHANGED = "unchanged"
STATUS_FILL = "fill"
STATUS_DIFFERENT = "different"
STATUS_ADD = "add"
STATUS_CONFLICT = "conflict"
STATUS_MISSING = "missing"
STATUS_LOCKED = "locked"


class MatchRequestError(Exception):
    """A request LibraryForge itself rejects (bad connection choice, bad input)."""

    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class ResolvedTarget:
    kind: MetadataTargetType
    obj: Any
    field_state_type: str
    current: dict[str, Any]

    @property
    def library(self):
        return self.obj.library

    @property
    def match_target(self) -> MatchTarget:
        year = self.current.get("year") if self.kind == MetadataTargetType.MOVIE else self.current.get("start_year")
        return MatchTarget(
            title=self.current.get("title") or "",
            original_title=self.current.get("original_title") or "",
            year=year if isinstance(year, int) else None,
            external_ids={
                str(key).casefold(): str(value)
                for key, value in (self.current.get("external_ids") or {}).items()
                if str(value).strip()
            },
        )

    def summary(self) -> dict[str, Any]:
        return {
            "type": self.kind.value,
            "id": str(self.obj.id),
            "library_id": str(self.obj.library_id),
            "title": self.current.get("title") or "",
            "year": self.match_target.year,
        }


# ---------------------------------------------------------------------------
# Target and connection resolution
# ---------------------------------------------------------------------------


def _movie_year(item: MediaItem) -> int | None:
    year = ((item.canonical_metadata or {}).get("semantic") or {}).get("year")
    if isinstance(year, int):
        return year
    return item.release_date.year if item.release_date else None


def _queryset(model, for_update: bool):
    queryset = model.objects.select_related("library")
    # Lock only the target row (not the joined library) while applying.
    return queryset.select_for_update(of=("self",)) if for_update else queryset


def resolve_target(*, user, target_type: str, target_id, for_update: bool = False) -> ResolvedTarget:
    """Load a movie or series owned by ``user``; anything else is a 404."""

    if target_type == MetadataTargetType.MOVIE.value:
        item = get_object_or_404(
            _queryset(MediaItem, for_update),
            id=target_id,
            library__owner=user,
            media_type=MediaItem.MediaType.MOVIE,
        )
        return ResolvedTarget(
            kind=MetadataTargetType.MOVIE,
            obj=item,
            field_state_type=CanonicalFieldState.TargetType.MEDIA_ITEM,
            current={
                "title": item.title,
                "original_title": item.original_title,
                "sort_title": item.sort_title,
                "release_date": item.release_date.isoformat() if item.release_date else None,
                "year": _movie_year(item),
                "description": item.description,
                "tagline": item.tagline,
                "content_rating": item.content_rating,
                "genres": list(item.genres or []),
                "studios": list(item.studios or []),
                "external_ids": dict(item.external_ids or {}),
            },
        )

    if target_type == MetadataTargetType.SERIES.value:
        series = get_object_or_404(
            _queryset(Series, for_update),
            id=target_id,
            library__owner=user,
        )
        return ResolvedTarget(
            kind=MetadataTargetType.SERIES,
            obj=series,
            field_state_type=CanonicalFieldState.TargetType.SERIES,
            current={
                "title": series.title,
                "original_title": series.original_title,
                "sort_title": series.sort_title,
                "start_year": series.start_year,
                "end_year": series.end_year,
                "description": series.description,
                "tagline": series.tagline,
                "content_rating": series.content_rating,
                "genres": list(series.genres or []),
                "studios": list(series.studios or []),
                "external_ids": dict(series.external_ids or {}),
            },
        )

    from django.http import Http404

    raise Http404("Unsupported metadata target.")


def _connection_rows(resolved: ResolvedTarget) -> list[tuple[dict[str, Any], Any]]:
    rows: list[tuple[dict[str, Any], Any]] = []
    for link in active_links_for_library(library=resolved.library, capability="metadata"):
        try:
            definition = get_provider_class(link.connection.provider).definition
        except ValueError:
            continue
        available = provider_supports_metadata_target(definition, resolved.kind)
        rows.append(
            (
                {
                    "connection_id": str(link.connection_id),
                    "connection_name": link.connection.name,
                    "provider": definition.key,
                    "provider_label": definition.label,
                    "status": link.connection.status,
                    "available": available,
                    "reason": "" if available else f"{definition.label} does not provide {resolved.kind.value} metadata.",
                    "attribution": definition.attribution,
                },
                link,
            )
        )
    return rows


def match_context(resolved: ResolvedTarget) -> dict[str, Any]:
    target = resolved.match_target
    return {
        "target": resolved.summary(),
        "connections": [row for row, _link in _connection_rows(resolved)],
        "search_defaults": {
            "query": target.title,
            "year": target.year,
            "original_title": target.original_title,
        },
    }


def _provider_for(resolved: ResolvedTarget, connection_id: str | None):
    available = [(row, link) for row, link in _connection_rows(resolved) if row["available"]]
    if connection_id:
        chosen = [(row, link) for row, link in available if row["connection_id"] == str(connection_id)]
        if not chosen:
            raise MatchRequestError(
                "Choose a provider connection that is enabled, assigned to this library for metadata, "
                f"and supports {resolved.kind.value} metadata."
            )
    elif len(available) == 1:
        chosen = available
    elif not available:
        raise MatchRequestError(
            f"No enabled provider connection for {resolved.kind.value} metadata is assigned to this library."
        )
    else:
        raise MatchRequestError("Choose which provider connection to use.")
    row, link = chosen[0]
    return row, provider_for_connection(link.connection)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def _parse_int(value: Any, name: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value).strip())
    except ValueError as exc:
        raise MatchRequestError(f"{name} must be a whole number.") from exc


def search_candidates(
    resolved: ResolvedTarget,
    *,
    connection_id: str | None,
    query: str | None,
    year: Any = None,
    page: Any = None,
    language: str | None = None,
) -> dict[str, Any]:
    connection, provider = _provider_for(resolved, connection_id)
    defaults = resolved.match_target
    search_query = (query if query is not None else defaults.title) or ""
    search_year = _parse_int(year, "Year")
    search_page = _parse_int(page, "Page") or 1

    candidates = provider.search_metadata(
        target_type=resolved.kind,
        query=search_query,
        year=search_year,
        language=language or None,
        page=search_page,
        limit=SEARCH_PAGE_SIZE,
    )
    target = resolved.match_target
    return {
        "target": resolved.summary(),
        "connection": connection,
        "query": " ".join(search_query.split()),
        "year": search_year,
        "page": search_page,
        "next_page": search_page + 1 if len(candidates) >= SEARCH_PAGE_SIZE else None,
        "results": [{**candidate.to_dict(), "match": match_hint(target, candidate)} for candidate in candidates],
    }


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _same(left: Any, right: Any) -> bool:
    if isinstance(left, str) and isinstance(right, str):
        return left.strip() == right.strip()
    return left == right


def _territory(value: str | None, language: str | None) -> str:
    if value:
        territory = value.strip().upper()
        if not _TERRITORY_PATTERN.fullmatch(territory):
            raise MatchRequestError("Territory must be a two-letter country code such as US or GB.")
        return territory
    if language and "-" in language:
        region = language.rsplit("-", 1)[1].upper()
        if _TERRITORY_PATTERN.fullmatch(region):
            return region
    return DEFAULT_TERRITORY


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def blocks_provider_update(state: CanonicalFieldState | None) -> bool:
    """Whether a field state stops a provider value from being offered.

    Manual (and other non-provider) locks always block. A lock written by a
    previous provider apply protects the value from library scans, but a new
    reviewed provider match may still replace it.
    """

    return bool(state and state.locked and state.source != CanonicalFieldState.Source.PROVIDER)


def field_states(resolved: ResolvedTarget) -> dict[str, CanonicalFieldState]:
    return {
        state.field_name: state
        for state in CanonicalFieldState.objects.filter(
            target_type=resolved.field_state_type,
            target_id=resolved.obj.id,
        )
    }


def target_revision(resolved: ResolvedTarget, states: dict[str, CanonicalFieldState] | None = None) -> str:
    """Fingerprint of the catalog values and locks a preview was built from."""

    states = field_states(resolved) if states is None else states
    return _digest(
        {
            "current": resolved.current,
            "locks": sorted(f"{name}:{state.source}" for name, state in states.items() if state.locked),
        }
    )


class _PreviewBuilder:
    def __init__(self, resolved: ResolvedTarget):
        self.resolved = resolved
        self.states = field_states(resolved)
        self.fields: list[dict[str, Any]] = []

    def _state(self, field_name: str) -> tuple[bool, str | None]:
        state = self.states.get(field_name.split(".")[0])
        return (blocks_provider_update(state), state.source if state else None)

    def scalar(
        self,
        field_name: str,
        label: str,
        group: str,
        proposed: Any,
        *,
        kind: str = "text",
        note: str = "",
        **extra: Any,
    ) -> dict[str, Any]:
        current = self.resolved.current.get(field_name)
        locked, source = self._state(field_name)
        if _is_empty(proposed):
            status = STATUS_MISSING
        elif _same(current, proposed):
            status = STATUS_UNCHANGED
        elif locked:
            status = STATUS_LOCKED
        elif _is_empty(current):
            status = STATUS_FILL
        else:
            status = STATUS_DIFFERENT
        row = {
            "field": field_name,
            "label": label,
            "group": group,
            "kind": kind,
            "current": current,
            "proposed": None if _is_empty(proposed) else proposed,
            "status": status,
            "selectable": status in {STATUS_FILL, STATUS_DIFFERENT},
            # Only empty catalog fields are suggested by default. Existing
            # values, including local and manual edits, are retained unless
            # the person chooses otherwise.
            "default_selected": status == STATUS_FILL,
            "locked": locked,
            "current_source": source,
            "note": note,
            **extra,
        }
        if status == STATUS_LOCKED:
            row["note"] = "Locked by a manual edit. Unlock it in the Metadata tab to use the provider's value."
        elif source == CanonicalFieldState.Source.PROVIDER and not row["note"]:
            row["note"] = "Currently from a previous provider match."
        self.fields.append(row)
        return row

    def collection(self, field_name: str, label: str, proposed: tuple[str, ...]) -> None:
        current = list(self.resolved.current.get(field_name) or [])
        known = {str(value).casefold() for value in current}
        additions = [value for value in proposed if value.casefold() not in known]
        locked, source = self._state(field_name)
        if not proposed:
            status = STATUS_MISSING
        elif not additions:
            status = STATUS_UNCHANGED
        elif locked:
            status = STATUS_LOCKED
        elif not current:
            status = STATUS_FILL
        else:
            status = STATUS_ADD
        self.fields.append(
            {
                "field": field_name,
                "label": label,
                "group": "relationships",
                "kind": "list",
                "current": current,
                "proposed": list(proposed) or None,
                "additions": additions,
                # Existing entries are always kept; nothing is removed.
                "result": current + additions,
                "status": status,
                "selectable": status in {STATUS_FILL, STATUS_ADD},
                "default_selected": status == STATUS_FILL,
                "locked": locked,
                "current_source": source,
                "note": (
                    "Locked by a manual edit. Unlock it in the Metadata tab to add provider entries."
                    if status == STATUS_LOCKED
                    else "Adds new entries and keeps every existing one."
                    if status == STATUS_ADD
                    else ""
                ),
            }
        )

    def external_ids(self, detail: ProviderMetadata) -> None:
        current = {str(key).casefold(): str(value) for key, value in (self.resolved.current.get("external_ids") or {}).items()}
        proposed = {item.namespace: item.value for item in detail.external_ids}
        locked, source = self._state("external_ids")
        for namespace in list(proposed) + [key for key in current if key not in proposed]:
            value = proposed.get(namespace)
            existing = current.get(namespace)
            if value is None:
                status = STATUS_MISSING
            elif existing is not None and existing.strip().casefold() == value.casefold():
                status = STATUS_UNCHANGED
            elif existing:
                # A different identifier suggests a different work. It is
                # never offered as a silent overwrite.
                status = STATUS_CONFLICT
            elif locked:
                status = STATUS_LOCKED
            else:
                status = STATUS_FILL
            self.fields.append(
                {
                    "field": f"external_ids.{namespace}",
                    "label": _NAMESPACE_LABELS.get(namespace, f"{namespace} ID"),
                    "group": "external_ids",
                    "kind": "external_id",
                    "namespace": namespace,
                    "current": existing,
                    "proposed": value,
                    "status": status,
                    "selectable": status == STATUS_FILL,
                    "default_selected": status == STATUS_FILL,
                    "locked": locked,
                    "current_source": source,
                    "note": (
                        "This ID differs from the item's. Check that this is the same work."
                        if status == STATUS_CONFLICT
                        else "Locked by a manual edit."
                        if status == STATUS_LOCKED
                        else ""
                    ),
                }
            )


def build_preview(
    resolved: ResolvedTarget,
    *,
    connection_id: str | None,
    source_id: str,
    language: str | None = None,
    territory: str | None = None,
) -> dict[str, Any]:
    if not source_id:
        raise MatchRequestError("Choose a candidate to preview.")
    territory_code = _territory(territory, language)
    connection, provider = _provider_for(resolved, connection_id)
    detail = provider.get_metadata(target_type=resolved.kind, source_id=source_id, language=language or None)

    builder = _PreviewBuilder(resolved)
    builder.scalar("title", "Title", "identity", detail.title)
    builder.scalar("original_title", "Original title", "identity", detail.original_title)
    builder.scalar(
        "sort_title",
        "Sort title",
        "identity",
        detail.sort_title,
        note="" if detail.sort_title else f"{connection['provider_label']} doesn't supply a sort title.",
    )

    not_stored: list[dict[str, str]] = []
    if resolved.kind == MetadataTargetType.MOVIE:
        provider_year = detail.release_date.year if detail.release_date else None
        full_date = detail.release_date.isoformat() if detail.release_date and detail.release_date.precision == "day" else None
        current_year = resolved.current.get("year")
        builder.scalar(
            "release_date",
            "Release date",
            "identity",
            full_date,
            kind="date",
            note=(
                f"Also sets the year to {provider_year}."
                if full_date and provider_year and provider_year != current_year
                else ""
                if full_date or not detail.release_date
                else f"Only a partial date is available ({detail.release_date.isoformat()})."
            ),
            linked_fields=["year"] if full_date else [],
        )
        builder.scalar(
            "year",
            "Year",
            "identity",
            provider_year,
            kind="year",
            note="Kept consistent with the release date when both are applied.",
            linked_to="release_date",
        )
        if detail.runtime_minutes:
            not_stored.append(
                {
                    "label": "Runtime",
                    "value": f"{detail.runtime_minutes} min",
                    "note": "LibraryForge reads runtime from your media files.",
                }
            )
    else:
        builder.scalar(
            "start_year",
            "First aired",
            "identity",
            detail.release_date.year if detail.release_date else None,
            kind="year",
        )
        builder.scalar(
            "end_year",
            "Last aired",
            "identity",
            detail.end_date.year if detail.end_date else None,
            kind="year",
            note="" if detail.end_date else "No end date: the series may still be running.",
        )
        if detail.runtime_minutes:
            not_stored.append(
                {
                    "label": "Episode runtime",
                    "value": f"{detail.runtime_minutes} min",
                    "note": "Series don't have a runtime field. Episode runtimes come from your media files.",
                }
            )
        if detail.networks:
            not_stored.append(
                {
                    "label": "Networks",
                    "value": ", ".join(detail.networks),
                    "note": "The catalog has no networks field yet. Networks are not merged into studios.",
                }
            )

    builder.scalar("description", "Description", "descriptive", detail.overview, kind="longtext")
    builder.scalar("tagline", "Tagline", "descriptive", detail.tagline)

    ratings = [item.to_dict() for item in detail.content_ratings]
    rating = next((item.value for item in detail.content_ratings if item.territory == territory_code), None)
    others = ", ".join(f"{item.territory} {item.value}" for item in detail.content_ratings if item.territory != territory_code)

    # Without a US rating, estimate one from other countries' ratings. It is
    # offered for review but never pre-selected.
    estimate = None
    if not rating and territory_code == "US":
        estimate = estimate_us_rating(
            [(item.territory, item.value) for item in detail.content_ratings],
            tv=resolved.kind != MetadataTargetType.MOVIE,
        )

    rating_row = builder.scalar(
        "content_rating",
        "Content rating",
        "descriptive",
        rating or (estimate.value if estimate else None),
        kind="rating",
        territory=territory_code,
        options=ratings,
        estimated=estimate is not None,
        estimate=estimate.to_dict() if estimate else None,
        note=(
            f"{territory_code} rating."
            if rating
            else f"No {territory_code} rating. {estimate.describe()} Check it before saving."
            if estimate
            else f"No {territory_code} rating. Other countries: {others}."
            if others
            else ""
        ),
    )
    if estimate is not None:
        rating_row["default_selected"] = False
        if rating_row["status"] == STATUS_LOCKED:
            rating_row["note"] = "Locked by a manual edit. " + estimate.describe()

    builder.collection("genres", "Genres", detail.genres)
    builder.collection("studios", "Studios", detail.studios)
    builder.external_ids(detail)

    summary: dict[str, int] = {}
    for row in builder.fields:
        summary[row["status"]] = summary.get(row["status"], 0) + 1

    return {
        "target": resolved.summary(),
        "connection": connection,
        "source_id": detail.source_id,
        "territory": territory_code,
        "provider_metadata": detail.to_dict(),
        "fields": builder.fields,
        "not_stored": not_stored,
        "summary": summary,
        # Fingerprints let a later apply step refuse a stale review: the
        # catalog values/locks and the provider data must still match what
        # was shown here.
        "target_revision": target_revision(resolved, builder.states),
        "provider_snapshot": _digest(detail.to_dict()),
    }


def error_payload(error: MetadataProviderError) -> dict[str, Any]:
    return {"detail": error.message, "error": error.to_dict()}


ERROR_STATUS = {
    MetadataErrorCategory.UNSUPPORTED_TARGET: 400,
    MetadataErrorCategory.INVALID_REQUEST: 400,
    MetadataErrorCategory.NOT_FOUND: 404,
    MetadataErrorCategory.RATE_LIMITED: 429,
    MetadataErrorCategory.TIMEOUT: 504,
}
