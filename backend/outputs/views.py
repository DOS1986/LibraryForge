from django.shortcuts import get_object_or_404
from rest_framework import (
    permissions,
    status,
    viewsets,
)
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import (
    ValidationError,
)
from rest_framework.response import Response

from libraries.models import Library
from metadata.match_views import _run
from outputs.security import (
    ProjectionSecurityError,
    validate_projection_destination,
    validate_projection_for_run,
)

from .models import (
    OutputProfile,
    Projection,
)
from .serializers import (
    OutputProfileSerializer,
    ProjectionSerializer,
)
from .services.projection import (
    preview_projection,
    run_projection,
)
from .services.youtube_shows import (
    shows_plan,
    shows_sync,
)


class OutputProfileViewSet(
    viewsets.ModelViewSet
):
    serializer_class = (
        OutputProfileSerializer
    )

    permission_classes = [
        permissions.IsAuthenticated,
    ]

    pagination_class = None

    def get_queryset(self):
        return (
            OutputProfile.objects
            .filter(
                owner=self.request.user
            )
            .order_by("name")
        )

    def perform_create(
        self,
        serializer,
    ):
        serializer.save(
            owner=self.request.user
        )


class ProjectionViewSet(
    viewsets.ModelViewSet
):
    serializer_class = (
        ProjectionSerializer
    )

    permission_classes = [
        permissions.IsAuthenticated,
    ]

    pagination_class = None

    def get_queryset(self):
        queryset = (
            Projection.objects
            .filter(
                library__owner=(
                    self.request.user
                ),
                output_profile__owner=(
                    self.request.user
                ),
            )
            .select_related(
                "library",
                "output_profile",
            )
        )

        library_id = (
            self.request
            .query_params
            .get(
                "library"
            )
        )

        if library_id:
            queryset = queryset.filter(
                library_id=library_id
            )

        return queryset

    def _checked(self, request):
        projection = self.get_object()
        try:
            validate_projection_destination(
                library=projection.library,
                destination_path=projection.destination_path,
                user=request.user,
            )
            if projection.layout == Projection.Layout.TEMPLATE:
                validate_projection_for_run(
                    projection=projection,
                    user=request.user,
                )
        except ProjectionSecurityError as exc:
            raise ValidationError(
                {
                    "detail": str(exc)
                }
            ) from exc
        return projection

    @staticmethod
    def _template_only(projection):
        if projection.layout != Projection.Layout.TEMPLATE:
            raise ValidationError(
                {
                    "detail": (
                        "This projection uses the Channels as TV shows layout. "
                        "Use its sync instead."
                    )
                }
            )

    @action(
        detail=True,
        methods=["get"],
        url_path="shows-plan",
    )
    def shows_plan(
        self,
        request,
        pk=None,
    ):
        """What a sync would create, update, or remove (reads nothing on disk)."""

        projection = self._checked(request)
        return _run(
            lambda: shows_plan(
                projection,
                channel=request.query_params.get("channel") or None,
            )
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="shows-sync",
    )
    def shows_sync(
        self,
        request,
        pk=None,
    ):
        """Apply one batch (body: optional cursor, batch, channel)."""

        projection = self._checked(request)
        return _run(
            lambda: shows_sync(
                projection,
                cursor=request.data.get("cursor") or None,
                batch=request.data.get("batch"),
                channel=request.data.get("channel") or None,
            )
        )

    @action(
        detail=True,
        methods=["get"],
    )
    def preview(
        self,
        request,
        pk=None,
    ):
        projection = self._checked(request)
        self._template_only(projection)
        return Response(
            preview_projection(
                projection
            )
        )

    @action(
        detail=True,
        methods=["post"],
    )
    def run(
        self,
        request,
        pk=None,
    ):
        projection = self._checked(request)
        self._template_only(projection)
        result = run_projection(
            projection
        )

        return Response(
            result,
            status=status.HTTP_200_OK,
        )


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def library_youtube_shows_view(request, library_id):
    """GET lists the library's Channels as TV shows folders; POST creates one.

    Body: ``destination_path`` and optional ``name``. Videos are always
    hardlinked. A "Jellyfin" output profile is created if you have none.
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
        generate_nfo=True,
    )
    return Response(ProjectionSerializer(projection).data, status=status.HTTP_201_CREATED)
