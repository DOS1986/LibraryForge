"""The projection engine: stored plans, journaled runs, recovery.

A **plan** is built from the catalog and the projection's manifest and stored
with every action (generated NFO contents included). It changes nothing on
disk. A **run** applies exactly one reviewed plan in the background worker:

* the plan must be ready, unexpired, match its digest, and the projection's
  manifest must not have changed since it was built;
* each action records its intent in the journal before touching the disk,
  rechecks what it expects to find, then records the result;
* an interrupted run's intents let a later run adopt the files it left behind
  (a file is never adopted on its content alone);
* runs can be cancelled between actions.

Layouts supply the desired files (``outputs.services.youtube_shows`` for
online-video libraries, ``outputs.services.movies_tv`` for movies and TV);
the shared file operations live in ``outputs.services.fileops``.
"""

from __future__ import annotations

import hashlib
import json
import os
import unicodedata
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Count, Max
from django.utils import timezone

from jobs.models import ScanJob
from libraries.models import Library
from metadata.services import secure_nfo
from metadata.services.provider_match import MatchRequestError
from outputs.models import (
    Projection,
    ProjectionFile,
    ProjectionPlan,
    ProjectionPlanAction,
    ProjectionRun,
    ProjectionRunAction,
)
from outputs.security import ProjectionSecurityError, validate_projection_destination
from outputs.services import fileops, library_nfo, movies_tv, profiles
from outputs.services import youtube_shows as shows

PLAN_TTL = timedelta(minutes=int(os.environ.get("LIBRARYFORGE_PROJECTION_PLAN_MINUTES", "30") or 30))
PAGE_SIZE = 100
MAX_PAGE_SIZE = 500

Kind = ProjectionFile.Kind
Action = ProjectionPlanAction.Action

# Each layout plans its own files: plan(projection) -> actions, desired,
# findings, overview; filter_scope(actions, scope_id) narrows to one group.
LAYOUTS = {
    Projection.Layout.YOUTUBE_SHOWS: shows,
    Projection.Layout.MOVIES: movies_tv,
    Projection.Layout.TV: movies_tv,
    Projection.Layout.LIBRARY_NFO: library_nfo,
}
# Layouts that write into the library itself rather than an output folder.
IN_PLACE = {Projection.Layout.LIBRARY_NFO}

# Findings that stop a plan from being applied.
BLOCKING = "blocking"
WARNING = "warning"


def comparison_key(path: str) -> str:
    """Two paths with the same key are the same file on a case-insensitive share."""

    return unicodedata.normalize("NFC", path).casefold()


def manifest_revision(projection: Projection) -> str:
    stats = ProjectionFile.objects.filter(projection=projection).aggregate(count=Count("id"), latest=Max("updated_at"))
    return hashlib.sha256(f"{stats['count']}|{stats['latest']}".encode()).hexdigest()


def _finding(code: str, severity: str, message: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message}


# ---------------------------------------------------------------------------
# Building plans
# ---------------------------------------------------------------------------


def _policy_findings(projection: Projection, user) -> list[dict[str, str]]:
    findings = []
    library = projection.library
    if projection.layout not in LAYOUTS:
        findings.append(_finding("UNSUPPORTED_LAYOUT", BLOCKING, "This projection's layout isn't supported yet."))
    if not projection.enabled:
        findings.append(_finding("DISABLED", BLOCKING, "This projection is turned off. Turn it on to build a plan."))
    if projection.layout in IN_PLACE:
        return findings + LAYOUTS[projection.layout].policy_findings(projection)
    try:
        validate_projection_destination(library=library, destination_path=projection.destination_path, user=user)
    except ProjectionSecurityError as error:
        findings.append(_finding("OUTSIDE_OUTPUT_ROOT", BLOCKING, str(error)))
    if projection.link_mode == Projection.LinkMode.HARDLINK:
        if library.management_mode == Library.ManagementMode.READ_ONLY:
            findings.append(
                _finding(
                    "HARDLINK_READ_ONLY",
                    BLOCKING,
                    "Hardlinks aren't allowed for a Read Only library. Use copies, or switch the library to Sidecar Only.",
                )
            )
        elif not projection.hardlink_acknowledged:
            findings.append(
                _finding(
                    "HARDLINK_NOT_ACKNOWLEDGED",
                    BLOCKING,
                    "Confirm the hardlink policy first: a hardlink is the same file as the original, so nothing "
                    "should write into media through the output folder.",
                )
            )
    for code, problem in (
        ("SOURCE_UNAVAILABLE", secure_nfo.library_root_error(library)),
        ("DESTINATION_UNAVAILABLE", fileops.destination_error(projection)),
    ):
        if problem:
            findings.append(_finding(code, BLOCKING, problem))
    return findings


def verify_legacy_files(projection: Projection) -> dict[str, int]:
    """Check files written before run journals existed, once.

    A link must still be the same file as its source; a generated file must
    still have the recorded hash. Verified entries are kept; missing ones are
    forgotten (so the plan recreates them); anything else stays unverified and
    is never replaced or removed.
    """

    rows = list(
        ProjectionFile.objects.filter(projection=projection, ownership=ProjectionFile.Ownership.LEGACY_UNVERIFIED)
        .select_related("media_file")
    )
    result = {"verified": 0, "missing": 0, "unverified": 0}
    if not rows:
        return result
    try:
        root = Path(projection.destination_path).expanduser().resolve(strict=True)
        library_root = Path(projection.library.path).expanduser().resolve(strict=True)
    except OSError:
        return result
    verified, missing = [], []
    for row in rows:
        try:
            path = fileops._target(root, row.relative_path, create_parents=False)
            if not path.exists():
                missing.append(row.id)
                continue
            if row.kind == Kind.VIDEO:
                ok = row.media_file is not None and fileops._matches_source(
                    projection, fileops._source(library_root, row.media_file), path
                )
            else:
                ok = fileops._is_ours(path, row)
        except (OSError, fileops._Conflict):
            ok = False
        if ok:
            verified.append(row.id)
        else:
            result["unverified"] += 1
    ProjectionFile.objects.filter(id__in=verified).update(ownership=ProjectionFile.Ownership.LEGACY_VERIFIED)
    ProjectionFile.objects.filter(id__in=missing).delete()
    result["verified"], result["missing"] = len(verified), len(missing)
    return result


def _removals_allowed(projection: Projection, *, ignore_policy: bool = False) -> tuple[bool, str]:
    """Absence-based removals need a complete, current view of the library.

    ``ignore_policy`` is for a cleanup review, where you approve removing the
    files a "keep" policy held on to; the safety checks still apply.
    """

    library = projection.library
    if projection.stale_policy == Projection.StalePolicy.KEEP and not ignore_policy:
        return False, "This projection keeps stale files."
    if ScanJob.objects.filter(library=library, status__in=[ScanJob.Status.QUEUED, ScanJob.Status.DISCOVERING, ScanJob.Status.RUNNING]).exists():
        return False, "A scan of the library is in progress."
    latest = ScanJob.objects.filter(library=library).exclude(status=ScanJob.Status.QUEUED).order_by("-created_at").first()
    if latest is None or latest.status not in (ScanJob.Status.COMPLETED, ScanJob.Status.COMPLETED_WITH_ERRORS):
        return False, "The library's last scan didn't finish."
    if secure_nfo.library_root_error(library):
        return False, "The library folder can't be reached."
    return True, ""


def _guard(projection: Projection, actions: list, desired_files: set) -> tuple[list, list[dict[str, str]]]:
    """Turn removals whose source is gone into kept files unless removal is safe.

    A removal for a file that's merely renamed (its source is still wanted) is
    always allowed: the new name is created earlier in the same plan.
    """

    allowed, reason = _removals_allowed(projection)
    findings = []
    output, kept = [], 0
    for action in actions:
        row = action.row
        source_gone = (
            action.action == fileops.ACTION_DELETE
            and row is not None
            and row.media_file_id is not None
            and row.media_file_id not in desired_files
        )
        if source_gone and not allowed:
            action.action = Action.RETAIN
            kept += 1
        output.append(action)
    if kept:
        findings.append(_finding("STALE_KEPT", WARNING, f"{kept} file(s) whose source is gone are kept: {reason}"))
    return output, findings


def _desired_json(desired) -> dict[str, Any]:
    if desired is None:
        return {}
    return {
        "season": desired.season,
        "episode": desired.episode,
        "stream_index": desired.stream_index,
        "source_size": desired.media_file.size_bytes if desired.media_file else None,
        "source_path": desired.source_path,
        "fingerprint": desired.fingerprint,
        **(desired.extra or {}),
    }


def _cleanup(projection: Projection, planned: dict[str, Any]) -> tuple[list, list[dict[str, str]], dict[str, int]]:
    """A cleanup review: the kept files to remove, and owned files to put right.

    * Stale files (no longer needed) are removed even under a "keep" policy,
      because you approve this list; the scan and share checks still apply.
    * In an output folder, owned files that went missing are written again,
      and owned NFOs and images changed outside LibraryForge are rewritten
      with the edited file kept beside them as a backup. Changed videos are
      only reported: a hardlinked video is the library's own file.
    """

    allowed, reason = _removals_allowed(projection, ignore_policy=True)
    desired_files = {item.media_file.id for item in planned["desired"] if item.media_file is not None}
    summary = {"stale": 0, "stale_kept": 0, "missing": 0, "changed": 0, "changed_videos": 0}
    findings: list[dict[str, str]] = []
    actions = []
    # Exactly the files a regular plan keeps; other removals (a renamed file's
    # old name) belong with the regular plan that creates the new name.
    guarded, _ = _guard(projection, planned["actions"], desired_files)
    for action in guarded:
        if action.action != Action.RETAIN or action.row is None:
            continue
        if allowed:
            action.action = Action.DELETE
            action.reason = "No longer needed; removed in this cleanup if it's unchanged"
            summary["stale"] += 1
        else:
            action.action = Action.RETAIN
            summary["stale_kept"] += 1
        actions.append(action)
    if summary["stale_kept"]:
        findings.append(
            _finding("STALE_KEPT", WARNING, f"{summary['stale_kept']} kept file(s) can't be removed yet: {reason}")
        )

    if projection.layout not in IN_PLACE:
        root = fileops._destination_root(projection)
        desired = {item.path: item for item in planned["desired"]}
        # Files from before run history that couldn't be verified are never touched.
        rows = ProjectionFile.objects.filter(projection=projection).exclude(ownership=ProjectionFile.Ownership.LEGACY_UNVERIFIED)
        for row in rows.select_related("channel", "media_file"):
            item = desired.get(row.relative_path)
            if item is None or item.kind != row.kind:
                continue  # Stale (above) or replaced by the regular plan.
            try:
                path = fileops._target(root, row.relative_path, create_parents=False)
                exists = path.exists()
                if exists and fileops._is_ours(path, row):
                    continue
            except (fileops._Conflict, OSError):
                continue
            if not exists:
                summary["missing"] += 1
                kind = Action.RELINK if row.kind == Kind.VIDEO else Action.UPDATE
                actions.append(fileops.Action(kind, row.kind, row.relative_path, row.channel, item, row, reason="Missing from the folder; written again"))
            elif row.kind == Kind.VIDEO:
                summary["changed_videos"] += 1
            else:
                summary["changed"] += 1
                item.extra = {**(item.extra or {}), "overwrite": True}
                actions.append(
                    fileops.Action(
                        Action.UPDATE, row.kind, row.relative_path, row.channel, item, row,
                        reason="Changed outside LibraryForge; rewritten, and the changed file is kept as a backup",
                    )
                )
        if summary["changed_videos"]:
            findings.append(
                _finding(
                    "CHANGED_VIDEOS",
                    WARNING,
                    f"{summary['changed_videos']} video(s) in the folder changed outside LibraryForge. They're left alone; "
                    "check them in the library itself.",
                )
            )
    actions.sort(key=lambda action: action.sort_key)
    return actions, findings, summary


def build_plan(projection: Projection, *, user, channel: str | None = None, cleanup: bool = False) -> ProjectionPlan:
    """Plan the changes that bring the output up to date.

    ``cleanup`` builds a cleanup review instead (see ``_cleanup``).
    """

    findings = _policy_findings(projection, user)
    legacy: dict[str, int] = {}
    actions: list = []
    overview: dict[str, Any] = {}
    if not any(finding["severity"] == BLOCKING for finding in findings):
        legacy = verify_legacy_files(projection)
        layout = LAYOUTS[projection.layout]
        planned = layout.plan(projection)
        profile = profiles.for_target(projection.output_profile.target).describe()
        if cleanup:
            try:
                actions, cleanup_findings, summary = _cleanup(projection, planned)
            except (OSError, MatchRequestError) as error:
                actions, summary = [], {}
                cleanup_findings = [
                    _finding("DESTINATION_UNAVAILABLE", BLOCKING, getattr(error, "message", None) or str(error))
                ]
            findings.extend(cleanup_findings)
            overview = {"cleanup": summary, "profile": profile}
        else:
            findings.extend(planned.get("findings") or [])
            desired_files = {item.media_file.id for item in planned["desired"] if item.media_file is not None}
            actions, guard_findings = _guard(projection, layout.filter_scope(planned["actions"], channel), desired_files)
            findings.extend(guard_findings)
            overview = {**(planned.get("overview") or {}), "profile": profile}
    if legacy.get("unverified"):
        findings.append(
            _finding(
                "LEGACY_UNVERIFIED",
                WARNING,
                f"{legacy['unverified']} file(s) from before run history couldn't be verified and will be left alone.",
            )
        )

    counts: dict[str, int] = {}
    for action in actions:
        counts[action.action] = counts.get(action.action, 0) + 1
    status = ProjectionPlan.Status.BLOCKED if any(f["severity"] == BLOCKING for f in findings) else ProjectionPlan.Status.READY

    records = []
    for ordinal, action in enumerate(actions):
        desired = action.desired
        content = (desired.content or b"").decode("utf-8") if desired is not None and desired.content else ""
        row = action.row
        records.append(
            ProjectionPlanAction(
                ordinal=ordinal,
                action=action.action,
                kind=action.kind,
                relative_path=action.path,
                comparison_key=comparison_key(action.path),
                channel=action.channel,
                media_file=desired.media_file if desired is not None else (row.media_file if row else None),
                manifest_file=row,
                expected=(
                    {"size": row.size_bytes, "sha256": row.content_sha256, "kind": row.kind} if row is not None else {"exists": False}
                ),
                desired=_desired_json(desired),
                group_id=str(action.group_id or "")[:64],
                group_title=str(action.group_title or "")[:1024],
                content=content,
                content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest() if content else "",
                reason=_reason(action),
            )
        )
    digest = hashlib.sha256(
        json.dumps(
            [[r.ordinal, r.action, r.kind, r.relative_path, r.content_sha256, r.desired] for r in records],
            sort_keys=True,
            default=str,
        ).encode()
    ).hexdigest()

    with transaction.atomic():
        ProjectionPlan.objects.filter(projection=projection, status=ProjectionPlan.Status.READY).update(
            status=ProjectionPlan.Status.SUPERSEDED
        )
        plan = ProjectionPlan.objects.create(
            projection=projection,
            projection_name=projection.name,
            requested_by=user,
            status=status,
            scope={"cleanup": True} if cleanup else ({"channel": channel} if channel else {}),
            content_digest=digest,
            manifest_revision=manifest_revision(projection),
            counts=counts,
            findings=findings,
            overview=overview,
            expires_at=timezone.now() + PLAN_TTL,
        )
        for record in records:
            record.plan = plan
        ProjectionPlanAction.objects.bulk_create(records, batch_size=500)
        if projection.needs_preview and status == ProjectionPlan.Status.READY and not cleanup:
            Projection.objects.filter(pk=projection.pk).update(needs_preview=False)
    return plan


def _reason(action) -> str:
    if getattr(action, "reason", ""):
        return action.reason
    return {
        Action.CREATE: "New file",
        Action.UPDATE: "LibraryForge's values changed",
        Action.RELINK: "The source file was replaced",
        Action.REPLACE: "A different file belongs at this path",
        Action.DELETE: "No longer needed",
        Action.ARTWORK: "Channel artwork to fetch",
        Action.RETAIN: "Its source is gone; kept until removal is safe",
    }.get(action.action, "")


# ---------------------------------------------------------------------------
# Serializing
# ---------------------------------------------------------------------------


def _page(value: Any, default: int, maximum: int) -> int:
    try:
        number = int(value) if value not in (None, "") else default
    except (TypeError, ValueError) as exc:
        raise MatchRequestError("Page numbers must be whole numbers.") from exc
    return max(1, min(number, maximum))


def action_rows(
    queryset, *, page: Any = None, page_size: Any = None, action: str | None = None, search: str | None = None
) -> dict[str, Any]:
    if action:
        queryset = queryset.filter(action=action)
    if search:
        queryset = queryset.filter(relative_path__icontains=search.strip()[:200])
    size = _page(page_size, PAGE_SIZE, MAX_PAGE_SIZE)
    number = _page(page, 1, 1_000_000)
    total = queryset.count()
    rows = list(queryset.select_related("channel")[(number - 1) * size : number * size])
    return {
        "page": number,
        "page_size": size,
        "total": total,
        "next_page": number + 1 if number * size < total else None,
        "results": [
            {
                "ordinal": row.ordinal,
                "action": row.action,
                "kind": row.kind,
                "path": row.relative_path,
                "group": getattr(row, "group_title", "") or (row.channel.title if getattr(row, "channel", None) else ""),
                "group_id": getattr(row, "group_id", "") or (str(row.channel_id) if getattr(row, "channel_id", None) else None),
                "reason": row.reason,
            }
            for row in rows
        ],
    }


def plan_detail(plan: ProjectionPlan) -> dict[str, Any]:
    now = timezone.now()
    expired = plan.status == ProjectionPlan.Status.READY and plan.expires_at <= now
    return {
        "id": str(plan.id),
        "projection_id": str(plan.projection_id) if plan.projection_id else None,
        "projection_name": plan.projection_name,
        "status": "expired" if expired else plan.status,
        "scope": plan.scope,
        "digest": plan.content_digest,
        "counts": plan.counts,
        "total": sum(plan.counts.values()),
        "changes": sum(count for action, count in plan.counts.items() if action != Action.RETAIN),
        "findings": plan.findings,
        "overview": plan.overview,
        "created_at": plan.created_at.isoformat(),
        "expires_at": plan.expires_at.isoformat(),
        "actions": action_rows(plan.actions.all(), page_size=PAGE_SIZE),
    }


def run_detail(run: ProjectionRun) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "plan_id": str(run.plan_id) if run.plan_id else None,
        "projection_id": str(run.projection_id) if run.projection_id else None,
        "projection_name": run.projection_name,
        "status": run.status,
        "status_label": run.get_status_display(),
        "cancel_requested": run.cancel_requested,
        "total": run.total,
        "done": run.done,
        "counts": run.counts,
        "problems": run.problems[:200],
        "error": run.error,
        "created_at": run.created_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


# ---------------------------------------------------------------------------
# Requesting runs
# ---------------------------------------------------------------------------


def request_run(plan: ProjectionPlan, *, user, digest: str, idempotency_key: str) -> tuple[ProjectionRun, bool]:
    """Queue a run of ``plan``. Returns (run, created); a repeated key returns the same run."""

    projection = plan.projection
    if projection is None:
        raise MatchRequestError("This plan's projection no longer exists.", status=409)
    key = str(idempotency_key or "").strip()[:64]
    if not key:
        raise MatchRequestError("An idempotency key is required.")
    existing = ProjectionRun.objects.filter(projection=projection, idempotency_key=key).first()
    if existing is not None:
        if existing.plan_id != plan.id:
            raise MatchRequestError("That idempotency key was used for a different plan.", status=409)
        return existing, False
    if digest != plan.content_digest:
        raise MatchRequestError("The plan changed since you reviewed it. Review it again.", status=409)
    if plan.status == ProjectionPlan.Status.BLOCKED:
        raise MatchRequestError("This plan has blocking problems; fix them and build a new plan.", status=422)
    if plan.status != ProjectionPlan.Status.READY:
        raise MatchRequestError("This plan was replaced or already applied. Build a new plan.", status=409)
    if plan.expires_at <= timezone.now():
        raise MatchRequestError("This plan expired. Build a new plan.", status=409)
    if manifest_revision(projection) != plan.manifest_revision:
        raise MatchRequestError("The output changed since this plan was built. Build a new plan.", status=409)
    blocking = [f for f in _policy_findings(projection, user) if f["severity"] == BLOCKING]
    if blocking:
        raise MatchRequestError(blocking[0]["message"], status=409)
    try:
        with transaction.atomic():
            run = ProjectionRun.objects.create(
                plan=plan,
                projection=projection,
                projection_name=projection.name,
                requested_by=user,
                idempotency_key=key,
                total=plan.actions.exclude(action=Action.RETAIN).count(),
            )
    except IntegrityError as exc:
        raise MatchRequestError("A run for this projection is already queued or running.", status=409) from exc
    return run, True


def cancel_run(run: ProjectionRun) -> ProjectionRun:
    if run.status == ProjectionRun.Status.QUEUED:
        run.status = ProjectionRun.Status.CANCELLED
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "completed_at", "updated_at"])
    elif run.status == ProjectionRun.Status.RUNNING:
        run.cancel_requested = True
        run.save(update_fields=["cancel_requested", "updated_at"])
    return run


# ---------------------------------------------------------------------------
# Worker side
# ---------------------------------------------------------------------------


def claim_next_run(worker_id: str) -> ProjectionRun | None:
    with transaction.atomic():
        run = (
            ProjectionRun.objects.select_for_update(skip_locked=True)
            .filter(status=ProjectionRun.Status.QUEUED)
            .order_by("created_at")
            .first()
        )
        if run is None:
            return None
        run.status = ProjectionRun.Status.RUNNING
        run.worker_id = worker_id
        run.started_at = timezone.now()
        run.save(update_fields=["status", "worker_id", "started_at", "updated_at"])
    return run


def recover_interrupted_runs(live_worker_ids: set[str]) -> int:
    stale = ProjectionRun.objects.filter(status=ProjectionRun.Status.RUNNING).exclude(worker_id__in=live_worker_ids)
    return stale.update(
        status=ProjectionRun.Status.INTERRUPTED,
        completed_at=timezone.now(),
        error="The worker running this stopped. Build a new plan to finish; files it left are adopted only where its journal shows it created them.",
    )


def _rebuild(projection: Projection, record: ProjectionPlanAction):
    desired = None
    if record.action != Action.DELETE and record.kind != "artwork":
        desired = fileops.Desired(
            path=record.relative_path,
            kind=record.kind,
            channel=record.channel,
            media_file=record.media_file,
            content=record.content.encode("utf-8") if record.content else None,
            season=record.desired.get("season"),
            episode=record.desired.get("episode"),
            stream_index=record.desired.get("stream_index"),
            source_path=record.desired.get("source_path") or "",
            fingerprint=record.desired.get("fingerprint") or "",
            group_id=record.group_id,
            group_title=record.group_title,
        )
    return fileops.Action(
        record.action, record.kind, record.relative_path, record.channel, desired, record.manifest_file,
        group_id=record.group_id, group_title=record.group_title,
    )


def _precondition_problem(record: ProjectionPlanAction) -> str:
    """Why this action can't run as reviewed (the manifest or source changed), or ''."""

    row = None
    if record.manifest_file_id:
        row = ProjectionFile.objects.filter(id=record.manifest_file_id).first()
        if row is None:
            return "The output file's record changed since the plan was built."
        if row.size_bytes != record.expected.get("size") or row.content_sha256 != record.expected.get("sha256"):
            return "The output file changed since the plan was built."
    elif record.expected.get("exists") is False and record.action == Action.CREATE:
        if ProjectionFile.objects.filter(projection=record.plan.projection, relative_path=record.relative_path).exists():
            return "Another run created this file since the plan was built."
    planned_size = record.desired.get("source_size")
    if record.media_file_id and planned_size is not None and (
        record.media_file is None or record.media_file.size_bytes != planned_size
    ):
        return "The source file changed since the plan was built."
    return ""


def _adoptable(projection: Projection, path: str, run: ProjectionRun) -> bool:
    return ProjectionRunAction.objects.filter(
        run__projection=projection,
        relative_path=path,
        state=ProjectionRunAction.State.INTENT,
    ).exclude(run=run).exists()


def execute_run(run: ProjectionRun) -> ProjectionRun:
    projection = run.projection
    plan = run.plan
    counts: dict[str, int] = {}
    problems: list[dict[str, str]] = []

    def finish(status: str, error: str = "") -> ProjectionRun:
        run.status = status
        run.error = error
        run.counts = counts
        run.problems = problems
        run.completed_at = timezone.now()
        run.save()
        if projection is not None:
            fields = {"last_run_at": run.completed_at}
            if status == ProjectionRun.Status.SUCCEEDED:
                fields["last_successful_run"] = run
            Projection.objects.filter(pk=projection.pk).update(**fields)
        if plan is not None and status in (ProjectionRun.Status.SUCCEEDED, ProjectionRun.Status.COMPLETED_WITH_ERRORS):
            ProjectionPlan.objects.filter(pk=plan.pk).update(status=ProjectionPlan.Status.APPLIED)
        return run

    if projection is None or plan is None:
        return finish(ProjectionRun.Status.FAILED, "The projection or plan no longer exists.")
    if manifest_revision(projection) != plan.manifest_revision:
        return finish(ProjectionRun.Status.FAILED, "The output changed since the plan was built. Build a new plan.")
    blocking = [f for f in _policy_findings(projection, run.requested_by) if f["severity"] == BLOCKING]
    if blocking:
        return finish(ProjectionRun.Status.FAILED, blocking[0]["message"])
    in_place = projection.layout in IN_PLACE
    try:
        library_root = Path(projection.library.path).expanduser().resolve(strict=True)
        root = None if in_place else fileops._destination_root(projection)
    except (OSError, MatchRequestError) as error:
        return finish(ProjectionRun.Status.FAILED, getattr(error, "message", None) or secure_nfo.library_root_problem(error))

    records = plan.actions.exclude(action=Action.RETAIN).select_related("channel", "media_file", "plan__projection")
    for index, record in enumerate(records.iterator(chunk_size=200)):
        if index % 10 == 0:
            run.refresh_from_db(fields=["cancel_requested"])
            if run.cancel_requested:
                return finish(ProjectionRun.Status.CANCELLED, "Cancelled; files already done are recorded.")
        journal = ProjectionRunAction.objects.create(
            run=run,
            plan_action=record,
            ordinal=record.ordinal,
            action=record.action,
            kind=record.kind,
            relative_path=record.relative_path,
        )
        started = timezone.now()
        problem = _precondition_problem(record)
        if problem:
            result, state, message = "conflict", ProjectionRunAction.State.SKIPPED, problem
        else:
            try:
                with transaction.atomic():
                    if in_place:
                        result, message = LAYOUTS[projection.layout].apply_record(projection, record, library_root)
                    else:
                        notes: list[str] = []
                        result = fileops._apply(
                            projection,
                            root,
                            library_root,
                            _rebuild(projection, record),
                            allow_adopt=_adoptable(projection, record.relative_path, run),
                            overwrite=bool(record.desired.get("overwrite")),
                            notes=notes,
                        )
                        message = "Changed outside LibraryForge, so it was left in place." if result == "kept" else ""
                        message = notes[0] if notes else message
                    ProjectionFile.objects.filter(projection=projection, updated_at__gte=started).update(
                        ownership=ProjectionFile.Ownership.OWNED, last_run=run
                    )
                state = ProjectionRunAction.State.DONE
            except fileops._CrossDevice:
                journal.state, journal.result = ProjectionRunAction.State.FAILED, "failed"
                journal.message = "Hardlinks can't cross volumes."
                journal.save()
                return finish(
                    ProjectionRun.Status.FAILED,
                    "Hardlinks can't be made here: the output folder has to be on the same share and volume as the "
                    "library. Choose a destination next to the library folder, or use copies.",
                )
            except fileops._Conflict as error:
                result, state, message = "conflict", ProjectionRunAction.State.SKIPPED, str(error)
            except OSError as error:
                result, state, message = "failed", ProjectionRunAction.State.FAILED, error.strerror or str(error)
        journal.state, journal.result, journal.message = state, result, message
        journal.save(update_fields=["state", "result", "message", "updated_at"])
        counts[result] = counts.get(result, 0) + 1
        # Notes on successful actions (a backup kept) stay in the journal.
        if message and (state != ProjectionRunAction.State.DONE or result == "kept") and len(problems) < 500:
            problems.append({"path": record.relative_path, "action": record.action, "result": result, "message": message})
        run.done = index + 1
        run.counts = counts
        run.save(update_fields=["done", "counts", "updated_at"])

    failed = counts.get("failed", 0)
    return finish(ProjectionRun.Status.COMPLETED_WITH_ERRORS if failed else ProjectionRun.Status.SUCCEEDED)


def projection_summary(projection: Projection) -> dict[str, Any]:
    latest = ProjectionRun.objects.filter(projection=projection).first()
    active = ProjectionRun.objects.filter(projection=projection, status__in=ProjectionRun.ACTIVE).first()
    return {
        "latest_run": run_detail(latest) if latest else None,
        "active_run": run_detail(active) if active else None,
        "managed_files": ProjectionFile.objects.filter(projection=projection).count(),
        "unverified_files": ProjectionFile.objects.filter(
            projection=projection, ownership=ProjectionFile.Ownership.LEGACY_UNVERIFIED
        ).count(),
    }


__all__ = [
    "build_plan",
    "cancel_run",
    "claim_next_run",
    "comparison_key",
    "execute_run",
    "plan_detail",
    "recover_interrupted_runs",
    "request_run",
    "run_detail",
]
