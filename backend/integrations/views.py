from __future__ import annotations

from django.http import (
    Http404,
    HttpResponse,
)
from django.shortcuts import (
    get_object_or_404,
)
from django.utils import timezone

from rest_framework import (
    permissions,
    status,
    viewsets,
)
from rest_framework.decorators import (
    action,
    api_view,
    permission_classes,
)
from rest_framework.exceptions import (
    ValidationError,
)
from rest_framework.response import Response

from catalog.models import (
    Channel,
    OnlineVideo,
    Playlist,
)
from integrations.models import (
    IntegrationConnection,
    LibraryIntegration,
)
from integrations.registry import (
    provider_catalog,
)
from integrations.security import (
    fetch_remote_artwork,
    public_provider_error,
)
from integrations.serializers import (
    IntegrationConnectionSerializer,
    LibraryIntegrationSerializer,
)
from integrations.services import (
    active_links_for_library,
    provider_for_connection,
    transient_lookup,
)
from libraries.models import Library


MAX_REMOTE_ARTWORK_BYTES = (
    20 * 1024 * 1024
)


class IntegrationConnectionViewSet(
    viewsets.ModelViewSet
):
    pagination_class = None
    serializer_class = (
        IntegrationConnectionSerializer
    )
    permission_classes = [
        permissions.IsAuthenticated,
    ]

    def get_queryset(self):
        return (
            IntegrationConnection.objects
            .filter(
                owner=self.request.user
            )
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="test",
    )
    def test_connection(
        self,
        request,
        pk=None,
    ):
        connection = self.get_object()

        try:
            result = (
                provider_for_connection(
                    connection
                )
                .test_connection()
            )

        except Exception as exc:
            public_error = (
                public_provider_error(
                    exc
                )
            )

            connection.status = (
                IntegrationConnection
                .Status
                .ERROR
            )
            connection.last_error = (
                public_error
            )
            connection.last_tested_at = (
                timezone.now()
            )

            connection.save(
                update_fields=[
                    "status",
                    "last_error",
                    "last_tested_at",
                    "updated_at",
                ]
            )

            return Response(
                {
                    "ok": False,
                    "message": public_error,
                },
                status=(
                    status
                    .HTTP_400_BAD_REQUEST
                ),
            )

        connection.status = (
            IntegrationConnection
            .Status
            .CONNECTED
        )
        connection.last_error = ""
        connection.last_tested_at = (
            timezone.now()
        )

        connection.save(
            update_fields=[
                "status",
                "last_error",
                "last_tested_at",
                "updated_at",
            ]
        )

        return Response(
            result
        )


class LibraryIntegrationViewSet(
    viewsets.ModelViewSet
):
    pagination_class = None
    serializer_class = (
        LibraryIntegrationSerializer
    )
    permission_classes = [
        permissions.IsAuthenticated,
    ]

    def get_queryset(self):
        queryset = (
            LibraryIntegration.objects
            .filter(
                library__owner=(
                    self.request.user
                ),
                connection__owner=(
                    self.request.user
                ),
            )
            .select_related(
                "library",
                "connection",
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


@api_view(["GET"])
@permission_classes([
    permissions.IsAuthenticated
])
def providers(request):
    return Response(
        provider_catalog()
    )


def _target(
    library,
    target_type: str,
    target_id,
):
    if target_type == "channel":
        return get_object_or_404(
            Channel,
            id=target_id,
            library=library,
        )

    if target_type == "online_video":
        return get_object_or_404(
            OnlineVideo,
            id=target_id,
            library=library,
        )

    if target_type == "playlist":
        return get_object_or_404(
            Playlist,
            id=target_id,
            library=library,
        )

    raise ValidationError(
        {
            "target_type": (
                "Unsupported integration "
                "lookup target."
            )
        }
    )


def _target_for_source_id(
    *,
    library,
    target_type: str,
    source_id: str,
):
    if target_type == "channel":
        model = Channel

    elif target_type == "online_video":
        model = OnlineVideo

    elif target_type == "playlist":
        model = Playlist

    else:
        raise Http404(
            "Invalid integration artwork request."
        )

    return get_object_or_404(
        model,
        library=library,
        source_id=source_id,
    )


@api_view(["GET"])
@permission_classes([
    permissions.IsAuthenticated
])
def target_lookup(
    request,
    library_id,
    target_type,
    target_id,
):
    library = get_object_or_404(
        Library,
        id=library_id,
        owner=request.user,
    )

    target = _target(
        library,
        target_type,
        target_id,
    )

    source_id = str(
        getattr(
            target,
            "source_id",
            "",
        )
        or ""
    )

    if not source_id:
        raise ValidationError(
            {
                "detail": (
                    "Target does not have a "
                    "stable provider source ID."
                )
            }
        )

    return Response(
        {
            "target_type": target_type,
            "target_id": str(
                target.id
            ),
            "source_id": source_id,
            "results": transient_lookup(
                library=library,
                target_type=target_type,
                source_id=source_id,
            ),
        }
    )


@api_view(["GET"])
@permission_classes([
    permissions.IsAuthenticated
])
def library_artwork(
    request,
    library_id,
):
    library = get_object_or_404(
        Library,
        id=library_id,
        owner=request.user,
    )

    target_type = str(
        request.query_params.get(
            "target_type"
        )
        or ""
    )

    source_id = str(
        request.query_params.get(
            "source_id"
        )
        or ""
    )

    if (
        target_type
        not in {
            "channel",
            "online_video",
            "playlist",
        }
        or not source_id
    ):
        raise Http404(
            "Invalid integration artwork request."
        )

    # A browser-provided source_id must correspond to an object already
    # owned by this library. This prevents the artwork proxy from becoming
    # a generic credentialed provider request primitive.
    target = _target_for_source_id(
        library=library,
        target_type=target_type,
        source_id=source_id,
    )

    stable_source_id = str(
        target.source_id
        or ""
    )

    for link in active_links_for_library(
        library=library,
        capability="artwork",
    ):
        try:
            provider = provider_for_connection(
                link.connection
            )

            item = (
                provider.lookup_one(
                    target_type=target_type,
                    source_id=(
                        stable_source_id
                    ),
                )
                or {}
            )

            artwork_url = str(
                item.get(
                    "artwork_url"
                )
                or ""
            )

        except Exception:
            continue

        if not artwork_url:
            continue

        remote = fetch_remote_artwork(
            artwork_url=artwork_url,
            provider=provider,
            connection_provider=(
                link.connection.provider
            ),
            max_bytes=(
                MAX_REMOTE_ARTWORK_BYTES
            ),
        )

        if remote is None:
            continue

        response = HttpResponse(
            remote.body,
            content_type=(
                remote.content_type
            ),
        )

        response[
            "Cache-Control"
        ] = "private, max-age=3600"

        response[
            "X-Content-Type-Options"
        ] = "nosniff"

        return response

    raise Http404(
        "No assigned integration returned "
        "artwork for this item."
    )
