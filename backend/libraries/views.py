from django.db import IntegrityError

from rest_framework import (
    permissions,
    status,
    viewsets,
)

from rest_framework.decorators import action
from rest_framework.response import Response

from jobs.models import ScanJob

from jobs.serializers import (
    ScanJobSerializer,
)

from libraries.services.storage import (
    test_storage_capabilities,
)

from .models import Library
from .serializers import LibrarySerializer


ACTIVE_SCAN_STATUSES = [
    ScanJob.Status.QUEUED,
    ScanJob.Status.DISCOVERING,
    ScanJob.Status.RUNNING,
]


class LibraryViewSet(
    viewsets.ModelViewSet
):
    serializer_class = LibrarySerializer

    permission_classes = [
        permissions.IsAuthenticated,
    ]

    pagination_class = None

    def get_queryset(self):
        return (
            Library.objects
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

    @action(
        detail=False,
        methods=["post"],
        url_path="test-path",
    )
    def test_path(
        self,
        request,
    ):
        path = request.data.get(
            "path",
            "",
        )

        result = (
            test_storage_capabilities(
                path
            )
        )

        return Response(
            result,
            status=status.HTTP_200_OK,
        )

    @action(
        detail=True,
        methods=["post"],
    )
    def scan(
        self,
        request,
        pk=None,
    ):
        library = self.get_object()

        existing = (
            ScanJob.objects
            .filter(
                library=library,
                status__in=(
                    ACTIVE_SCAN_STATUSES
                ),
            )
            .order_by(
                "-created_at"
            )
            .first()
        )

        if existing:
            return Response(
                ScanJobSerializer(
                    existing
                ).data,
                status=status.HTTP_200_OK,
            )

        try:
            job = ScanJob.objects.create(
                library=library,
                requested_by=request.user,
            )

            response_status = (
                status.HTTP_202_ACCEPTED
            )

        except IntegrityError:
            job = (
                ScanJob.objects
                .filter(
                    library=library,
                    status__in=(
                        ACTIVE_SCAN_STATUSES
                    ),
                )
                .order_by(
                    "-created_at"
                )
                .first()
            )

            if job is None:
                raise

            response_status = (
                status.HTTP_200_OK
            )

        return Response(
            ScanJobSerializer(
                job
            ).data,
            status=response_status,
        )
