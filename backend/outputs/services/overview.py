"""The Outputs page: every projection's state, the output roots, and recent runs.

Reads only. Root availability is checked with a short timeout so an
unreachable share can't hang the page.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from outputs.models import (
    Projection,
    ProjectionPlan,
    ProjectionPlanAction,
    ProjectionRun,
)
from outputs.security import _inside, _resolve, confined_output_folder
from outputs.services import engine

ROOT_TIMEOUT_SECONDS = 3
RECENT_RUNS = 25


def configured_roots() -> list[str]:
    return [str(value).strip() for value in getattr(settings, "LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS", []) if str(value).strip()]


def _state(path: str) -> str:
    """``ready`` (the folder exists), ``creatable`` (its parent does, so the
    first run creates it), or ``missing``."""

    folder = Path(path).expanduser()
    if folder.is_dir():
        return "ready"
    return "creatable" if not folder.exists() and folder.parent.is_dir() else "missing"


def _states(paths: list[str]) -> dict[str, str]:
    """Each path's state, or ``not_answering`` when it didn't answer in time."""

    if not paths:
        return {}
    executor = ThreadPoolExecutor(max_workers=min(len(paths), 8))
    futures = {path: executor.submit(_state, path) for path in paths}
    wait(futures.values(), timeout=ROOT_TIMEOUT_SECONDS)
    executor.shutdown(wait=False, cancel_futures=True)
    result: dict[str, str] = {}
    for path, future in futures.items():
        if not future.done():
            result[path] = "not_answering"
            continue
        try:
            result[path] = future.result()
        except OSError:
            result[path] = "missing"
    return result


def output_roots(projections: list[Projection]) -> list[dict[str, Any]]:
    roots = configured_roots()
    states = _states(roots)
    destinations = []
    for projection in projections:
        if projection.layout == Projection.Layout.LIBRARY_NFO or not projection.destination_path:
            continue
        try:
            destinations.append(confined_output_folder(projection.destination_path))
        except (OSError, ValueError):
            # Outside every allowed root, so it counts toward none of them.
            continue
    results = []
    for root in roots:
        try:
            resolved = _resolve(root)
            count = sum(1 for destination in destinations if _inside(destination, resolved))
        except (OSError, ValueError):
            count = 0
        state = states.get(root, "missing")
        results.append(
            {
                "path": root,
                "state": state,
                "available": True if state == "ready" else None if state == "not_answering" else False,
                "projections": count,
            }
        )
    return results


def _plan_summary(plan: ProjectionPlan | None) -> dict[str, Any] | None:
    if plan is None:
        return None
    expired = plan.status == ProjectionPlan.Status.READY and plan.expires_at <= timezone.now()
    return {
        "id": str(plan.id),
        "status": "expired" if expired else plan.status,
        "cleanup": bool((plan.scope or {}).get("cleanup")),
        "counts": plan.counts,
        "changes": sum(count for action, count in plan.counts.items() if action != ProjectionPlanAction.Action.RETAIN),
        "blocking": [finding["message"] for finding in plan.findings if finding.get("severity") == engine.BLOCKING][:3],
        "created_at": plan.created_at.isoformat(),
    }


def _projection(projection: Projection) -> dict[str, Any]:
    library = projection.library
    return {
        "id": str(projection.id),
        "name": projection.name,
        "library_id": str(library.id),
        "library_name": library.name,
        "library_content_type": library.content_type,
        "library_path": library.path,
        "layout": projection.layout,
        "layout_label": projection.get_layout_display(),
        "in_place": projection.layout in engine.IN_PLACE,
        "target": projection.output_profile.target,
        "target_label": projection.output_profile.get_target_display(),
        "destination_path": projection.destination_path,
        "link_mode_label": projection.get_link_mode_display(),
        "stale_policy": projection.stale_policy,
        "enabled": projection.enabled,
        "needs_preview": projection.needs_preview,
        "latest_plan": _plan_summary(ProjectionPlan.objects.filter(projection=projection).first()),
        **engine.projection_summary(projection),
    }


def _run(run: ProjectionRun) -> dict[str, Any]:
    projection = run.projection
    return {
        **engine.run_detail(run),
        "library_id": str(projection.library_id) if projection else None,
        "library_name": projection.library.name if projection else "",
        "layout": projection.layout if projection else "",
        "in_place": bool(projection and projection.layout in engine.IN_PLACE),
        "cleanup": bool(run.plan and (run.plan.scope or {}).get("cleanup")),
    }


def owned_runs(user):
    """Runs of the user's projections, and runs they made of since-deleted ones."""

    return ProjectionRun.objects.filter(
        Q(projection__library__owner=user) | Q(projection__isnull=True, requested_by=user)
    )


def outputs_overview(user) -> dict[str, Any]:
    projections = list(
        Projection.objects.filter(library__owner=user, output_profile__owner=user)
        .exclude(layout=Projection.Layout.TEMPLATE)
        .select_related("library", "output_profile")
        .order_by("library__name", "name")
    )
    runs = owned_runs(user).select_related("projection__library", "plan")[:RECENT_RUNS]
    return {
        "roots": output_roots(projections),
        "projections": [_projection(projection) for projection in projections],
        "recent_runs": [_run(run) for run in runs],
    }
