from rest_framework import (
    permissions,
    viewsets,
)
from rest_framework.decorators import action
from rest_framework.response import Response

from libraryforge.pagination import (
    LibraryForgePagination,
)

from .models import ScanJob
from .serializers import ScanJobSerializer
from .services import cancel_job, worker_status


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

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Cancel a queued, running, or stalled scan."""

        job = cancel_job(self.get_object())
        return Response(ScanJobSerializer(job, context=self.get_serializer_context()).data)

    @action(detail=False, methods=["get"])
    def worker(self, request):
        """Whether a scan worker is running, so the UI can explain queued scans."""

        data = worker_status()
        data["queued_jobs"] = self.get_queryset().filter(status=ScanJob.Status.QUEUED).count()
        return Response(data)
