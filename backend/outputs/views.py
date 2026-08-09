from rest_framework import (
    permissions,
    status,
    viewsets,
)

from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

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
                )
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

    def perform_create(
        self,
        serializer,
    ):
        library = (
            serializer
            .validated_data[
                "library"
            ]
        )

        output_profile = (
            serializer
            .validated_data[
                "output_profile"
            ]
        )

        if (
            library.owner_id
            != self.request.user.id
        ):
            raise ValidationError(
                "Invalid library."
            )

        if (
            output_profile.owner_id
            != self.request.user.id
        ):
            raise ValidationError(
                "Invalid output profile."
            )

        serializer.save()

    @action(
        detail=True,
        methods=["get"],
    )
    def preview(
        self,
        request,
        pk=None,
    ):
        projection = self.get_object()

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
        projection = self.get_object()

        result = run_projection(
            projection
        )

        return Response(
            result,
            status=status.HTTP_200_OK,
        )
