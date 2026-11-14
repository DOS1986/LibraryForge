"""Apply a reviewed metadata-provider preview to a movie or series.

This is the only metadata-provider operation that writes catalog data. It
never trusts the browser's values: it rebuilds the preview on the server,
refuses stale reviews, accepts only field *names* that the preview marked
selectable, and writes the server-side values together with provenance and a
change-history entry in one transaction.

Order of operations:

1. Replay check: a repeated operation ID returns the recorded result.
2. Rebuild the preview (provider retrieval happens here, outside any
   transaction) and compare its fingerprints with the reviewed ones.
3. Validate the chosen fields and their consistency rules.
4. In one transaction, lock the target row, re-check its revision, write the
   values, mark each applied field as provider-sourced (locked against library
   scans), and record a change set keyed by the operation ID.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from catalog.models import CanonicalFieldState, MetadataChangeSet
from catalog.services.canonical import movie_detail, series_detail
from metadata.providers.types import MetadataTargetType
from metadata.services.provider_match import (
    MatchRequestError,
    ResolvedTarget,
    build_preview,
    resolve_target,
    target_revision,
)

MAX_APPLY_FIELDS = 60


class ApplyConflict(MatchRequestError):
    """The review is stale or the operation ID was reused for another change."""

    def __init__(self, message: str, *, code: str):
        super().__init__(message, status=409)
        self.code = code


def _detail(resolved: ResolvedTarget) -> dict[str, Any]:
    resolved.obj.refresh_from_db()
    return movie_detail(resolved.obj) if resolved.kind == MetadataTargetType.MOVIE else series_detail(resolved.obj)


def _serialize_change_set(change_set: MetadataChangeSet) -> dict[str, Any]:
    return {
        "id": str(change_set.id),
        "source": change_set.source,
        "source_ref": change_set.source_ref,
        "operation_id": str(change_set.operation_id) if change_set.operation_id else None,
        "fields": sorted(change_set.changes),
        "changes": change_set.changes,
        "note": change_set.note,
        "created_at": change_set.created_at,
    }


def _same_request(change_set: MetadataChangeSet, request: dict[str, Any]) -> bool:
    recorded = change_set.details or {}
    return (
        sorted(recorded.get("requested_fields") or []) == sorted(set(request["fields"]))
        and all(
            (recorded.get(key) or "") == (request.get(key) or "")
            for key in ("source_id", "territory", "target_revision", "provider_snapshot")
        )
    )


def _replay(resolved: ResolvedTarget, user, request: dict[str, Any]) -> dict[str, Any] | None:
    """Return the recorded result for a repeated operation ID, or None if it is new."""

    existing = MetadataChangeSet.objects.filter(operation_id=request["operation_id"]).first()
    if existing is None:
        return None
    if (
        existing.changed_by_id != user.pk
        or existing.target_id != resolved.obj.id
        or not _same_request(existing, request)
    ):
        raise ApplyConflict(
            "This operation ID was already used for a different change. Review the match again.",
            code="operation_reused",
        )
    return {
        "applied": True,
        "replayed": True,
        "change_set": _serialize_change_set(existing),
        "detail": _detail(resolved),
    }


def _effective_fields(resolved: ResolvedTarget, rows: dict[str, dict[str, Any]], requested: list[str]) -> list[str]:
    unknown = [name for name in requested if name not in rows]
    if unknown:
        raise MatchRequestError("Unknown fields: " + ", ".join(sorted(unknown)[:10]) + ".")
    blocked = [name for name in requested if not rows[name]["selectable"]]
    if blocked:
        labels = ", ".join(sorted(rows[name]["label"] for name in blocked)[:10])
        raise MatchRequestError(f"These fields can't be applied from this preview: {labels}.")

    fields = set(requested)
    if resolved.kind == MetadataTargetType.MOVIE and "release_date" in fields:
        year_row = rows.get("year")
        if year_row and year_row["selectable"]:
            # The release date's year comes along so the two stay consistent.
            fields.add("year")
        elif year_row and year_row["status"] == "locked":
            raise MatchRequestError("The year is locked by a manual edit and would disagree with this release date.")
    return sorted(fields)


def _new_values(resolved: ResolvedTarget, rows: dict[str, dict[str, Any]], fields: list[str]) -> dict[str, Any]:
    """Server-side values for the chosen fields, grouped by catalog field."""

    values: dict[str, Any] = {}
    external_ids = dict(resolved.current.get("external_ids") or {})
    external_changed = False
    for name in fields:
        row = rows[name]
        if row["kind"] == "external_id":
            external_ids[row["namespace"]] = row["proposed"]
            external_changed = True
        elif row["kind"] == "list":
            values[name] = list(row["result"])
        else:
            values[name] = row["proposed"]
    if external_changed:
        values["external_ids"] = external_ids

    if resolved.kind == MetadataTargetType.MOVIE:
        release_date = values.get("release_date", resolved.current.get("release_date"))
        year = values.get("year", resolved.current.get("year"))
        if release_date and year and datetime.date.fromisoformat(release_date).year != year:
            raise MatchRequestError("The year and release date would disagree. Apply both together.")
    else:
        start = values.get("start_year", resolved.current.get("start_year"))
        end = values.get("end_year", resolved.current.get("end_year"))
        if start and end and end < start:
            raise MatchRequestError("The last-aired year would come before the first-aired year.")
    return values


def _write(resolved: ResolvedTarget, values: dict[str, Any]) -> dict[str, dict[str, Any]]:
    obj = resolved.obj
    changes: dict[str, dict[str, Any]] = {}
    for name, new in values.items():
        old = resolved.current.get(name)
        if old == new:
            continue
        changes[name] = {"old": old, "new": new}
        if resolved.kind == MetadataTargetType.MOVIE and name == "year":
            canonical = dict(obj.canonical_metadata or {})
            semantic = dict(canonical.get("semantic") or {})
            semantic["kind"] = "movie"
            semantic["year"] = new
            canonical["semantic"] = semantic
            obj.canonical_metadata = canonical
        elif name == "release_date":
            obj.release_date = datetime.date.fromisoformat(new) if new else None
        else:
            setattr(obj, name, new)
    if changes:
        obj.save()
    return changes


def apply_preview(*, user, target_type: str, target_id, request: dict[str, Any]) -> dict[str, Any]:
    resolved = resolve_target(user=user, target_type=target_type, target_id=target_id)
    replay = _replay(resolved, user, request)
    if replay is not None:
        return replay

    retrieved_at = timezone.now()
    preview = build_preview(
        resolved,
        connection_id=request.get("connection"),
        source_id=request["source_id"],
        language=request.get("language"),
        territory=request.get("territory"),
    )
    if preview["provider_snapshot"] != request["provider_snapshot"]:
        raise ApplyConflict(
            f"{preview['connection']['provider_label']}'s details changed since you reviewed them. Review the match again.",
            code="provider_changed",
        )
    if preview["target_revision"] != request["target_revision"]:
        raise ApplyConflict(
            "This item changed since you reviewed the match. Review it again.",
            code="target_changed",
        )

    rows = {row["field"]: row for row in preview["fields"]}
    requested = sorted(set(request["fields"]))
    fields = _effective_fields(resolved, rows, requested)
    values = _new_values(resolved, rows, fields)

    connection = preview["connection"]
    source_ref = f"{connection['provider']}:{resolved.kind.value}:{preview['source_id']}"[:255]
    try:
        with transaction.atomic():
            locked = resolve_target(user=user, target_type=target_type, target_id=target_id, for_update=True)
            if target_revision(locked) != request["target_revision"]:
                raise ApplyConflict(
                    "This item changed while the match was being applied. Review it again.",
                    code="target_changed",
                )
            changes = _write(locked, values)

            for name, change in changes.items():
                # Provider values are locked against library scans but remain
                # replaceable by a later reviewed provider match.
                CanonicalFieldState.objects.update_or_create(
                    target_type=locked.field_state_type,
                    target_id=locked.obj.id,
                    field_name=name,
                    defaults={
                        "source": CanonicalFieldState.Source.PROVIDER,
                        "source_ref": source_ref,
                        "value_snapshot": change["new"],
                        "locked": True,
                        "updated_by": user,
                    },
                )

            change_set = MetadataChangeSet.objects.create(
                target_type=locked.field_state_type,
                target_id=locked.obj.id,
                source=MetadataChangeSet.Source.PROVIDER,
                source_ref=source_ref,
                operation_id=request["operation_id"],
                changes=changes,
                note=f"Applied from {connection['provider_label']} ({preview['source_id']}).",
                changed_by=user,
                details={
                    "provider": connection["provider"],
                    "provider_label": connection["provider_label"],
                    "connection_id": connection["connection_id"],
                    "connection_name": connection["connection_name"],
                    "target_type": resolved.kind.value,
                    "source_id": request["source_id"],
                    "territory": request.get("territory") or "",
                    "resolved_territory": preview["territory"],
                    "retrieved_at": retrieved_at.isoformat(),
                    "requested_fields": requested,
                    "applied_fields": sorted(changes),
                    "target_revision": request["target_revision"],
                    "provider_snapshot": request["provider_snapshot"],
                },
            )
    except IntegrityError:
        # A concurrent submission with the same operation ID won the race.
        replay = _replay(resolved, user, request)
        if replay is None:
            raise
        return replay

    return {
        "applied": True,
        "replayed": False,
        "change_set": _serialize_change_set(change_set),
        "detail": _detail(locked),
    }
