"""Output profiles, projections, plans, and runs.

Configuration endpoints never touch disk. Changing output always goes
through a stored plan that you review, then a run of exactly that plan in the
background worker.
"""

from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from libraries.models import Library
from metadata.match_views import _run
from outputs.security import ProjectionSecurityError, validate_projection_destination
from outputs.services import engine

from .models import OutputProfile, Projection, ProjectionPlan, ProjectionRun
from .serializers import OutputProfileSerializer, ProjectionSerializer


class OutputProfileViewSet(viewsets.ModelViewSet):
    serializer_class = OutputProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return OutputProfile.objects.filter(owner=self.request.user).order_by("name")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class ProjectionViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectionSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        queryset = Projection.objects.filter(
            library__owner=self.request.user,
            output_profile__owner=self.request.user,
        ).select_related("library", "output_profile")
        library_id = self.request.query_params.get("library")
        if library_id:
            queryset = queryset.filter(library_id=library_id)
        return queryset

    @action(detail=True, methods=["get", "post"])
    def plans(self, request, pk=None):
        """POST builds a plan (body: optional ``channel``); GET returns the newest."""

        projection = self.get_object()
        if request.method == "POST":
            channel = str(request.data.get("channel") or "").strip() or None
            return _run(lambda: engine.plan_detail(engine.build_plan(projection, user=request.user, channel=channel)))
        plan = ProjectionPlan.objects.filter(projection=projection).first()
        return Response(engine.plan_detail(plan) if plan else None)

    @action(detail=True, methods=["get"])
    def runs(self, request, pk=None):
        """Recent runs, newest first, and the projection's file summary."""

        projection = self.get_object()
        runs = ProjectionRun.objects.filter(projection=projection)[:20]
        return Response(
            {
                **engine.projection_summary(projection),
                "results": [engine.run_detail(run) for run in runs],
            }
        )


def _owned_plan(request, plan_id) -> ProjectionPlan:
    return get_object_or_404(ProjectionPlan, id=plan_id, projection__library__owner=request.user)


def _owned_run(request, run_id) -> ProjectionRun:
    return get_object_or_404(ProjectionRun, id=run_id, projection__library__owner=request.user)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def plan_detail_view(request, plan_id):
    return Response(engine.plan_detail(_owned_plan(request, plan_id)))


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def plan_actions_view(request, plan_id):
    plan = _owned_plan(request, plan_id)
    params = request.query_params
    return _run(
        lambda: engine.action_rows(
            plan.actions.all(), page=params.get("page"), page_size=params.get("page_size"), action=params.get("action") or None
        )
    )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def plan_run_view(request, plan_id):
    """Queue a run of a reviewed plan (body: ``digest``, ``idempotency_key``)."""

    plan = _owned_plan(request, plan_id)

    def queue():
        run, _created = engine.request_run(
            plan,
            user=request.user,
            digest=str(request.data.get("digest") or ""),
            idempotency_key=str(request.data.get("idempotency_key") or ""),
        )
        return engine.run_detail(run)

    response = _run(queue)
    if response.status_code == status.HTTP_200_OK:
        response.status_code = status.HTTP_202_ACCEPTED
    return response


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def run_detail_view(request, run_id):
    return Response(engine.run_detail(_owned_run(request, run_id)))


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def run_actions_view(request, run_id):
    run = _owned_run(request, run_id)
    params = request.query_params
    queryset = run.actions.all()
    if params.get("problems"):
        queryset = queryset.exclude(message="")
    size = engine._page(params.get("page_size"), engine.PAGE_SIZE, engine.MAX_PAGE_SIZE)
    page = engine._page(params.get("page"), 1, 1_000_000)
    total = queryset.count()
    rows = queryset[(page - 1) * size : page * size]
    return Response(
        {
            "page": page,
            "page_size": size,
            "total": total,
            "next_page": page + 1 if page * size < total else None,
            "results": [
                {
                    "ordinal": row.ordinal,
                    "action": row.action,
                    "kind": row.kind,
                    "path": row.relative_path,
                    "state": row.state,
                    "result": row.result,
                    "message": row.message,
                }
                for row in rows
            ],
        }
    )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def run_cancel_view(request, run_id):
    return Response(engine.run_detail(engine.cancel_run(_owned_run(request, run_id))))


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def library_youtube_shows_view(request, library_id):
    """GET lists the library's Channels as TV shows folders; POST creates one.

    Body: ``destination_path`` and optional ``name``. Videos are hardlinked
    once the hardlink policy is acknowledged on the projection. A "Jellyfin"
    output profile is created if you have none.
    """

    library = get_object_or_404(Library, id=library_id, owner=request.user)
    if request.method == "GET":
        projections = Projection.objects.filter(
            library=library, layout=Projection.Layout.YOUTUBE_SHOWS
        ).select_related("library", "output_profile")
        return Response(ProjectionSerializer(projections, many=True).data)

    if library.content_type not in ("online_video", "mixed"):
        raise ValidationError({"detail": "Channels as TV shows needs an online video library."})
    destination = str(request.data.get("destination_path") or "").strip()
    name = " ".join(str(request.data.get("name") or "Jellyfin YouTube shows").split())[:255]
    try:
        validate_projection_destination(library=library, destination_path=destination, user=request.user)
    except ProjectionSecurityError as exc:
        raise ValidationError({"destination_path": str(exc)}) from exc
    if Projection.objects.filter(library=library, destination_path=destination).exists():
        raise ValidationError({"destination_path": "This library already has a projection to that folder."})

    profile = (
        OutputProfile.objects.filter(owner=request.user, target=OutputProfile.Target.JELLYFIN).order_by("name").first()
    )
    if profile is None:
        profile, _created = OutputProfile.objects.get_or_create(
            owner=request.user,
            name="Jellyfin",
            defaults={"target": OutputProfile.Target.JELLYFIN, "nfo_root_element": "episodedetails"},
        )
    projection = Projection.objects.create(
        library=library,
        output_profile=profile,
        name=name,
        destination_path=destination,
        layout=Projection.Layout.YOUTUBE_SHOWS,
        link_mode=Projection.LinkMode.HARDLINK,
        hardlink_acknowledged=bool(request.data.get("hardlink_acknowledged")),
        generate_nfo=True,
    )
    return Response(ProjectionSerializer(projection).data, status=status.HTTP_201_CREATED)
