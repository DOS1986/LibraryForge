from rest_framework import (
    permissions,
    viewsets,
)

from libraryforge.pagination import (
    LibraryForgePagination,
)

from .models import ScanJob
from .serializers import ScanJobSerializer


class ScanJobViewSet(
    viewsets.ReadOnlyModelViewSet
):
    serializer_class = ScanJobSerializer

    permission_classes = [
        permissions.IsAuthenticated,
    ]

    pagination_class = (
        LibraryForgePagination
    )

    def get_queryset(self):
        queryset = (
            ScanJob.objects
            .filter(
                library__owner=(
                    self.request.user
                )
            )
            .select_related(
                "library"
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
