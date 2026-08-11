from __future__ import annotations

import mimetypes
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from catalog.models import Channel, OnlineVideo, Playlist
from integrations.models import IntegrationConnection, LibraryIntegration
from integrations.registry import provider_catalog
from integrations.serializers import IntegrationConnectionSerializer, LibraryIntegrationSerializer
from integrations.services import active_links_for_library, provider_for_connection, transient_lookup
from libraries.models import Library


MAX_REMOTE_ARTWORK_BYTES = 20 * 1024 * 1024
YOUTUBE_IMAGE_HOST_SUFFIXES = (
    ".ytimg.com",
    ".ggpht.com",
    ".googleusercontent.com",
)


def _allowed_artwork_url(*, artwork_url: str, provider, connection_provider: str) -> bool:
    parsed = urlparse(artwork_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False

    hostname = parsed.hostname.casefold()
    if hostname.endswith(YOUTUBE_IMAGE_HOST_SUFFIXES):
        return True

    if connection_provider == "tubearchivist":
        base = urlparse(getattr(provider, "base_url", ""))
        return (parsed.scheme, parsed.netloc) == (base.scheme, base.netloc)

    return False


class IntegrationConnectionViewSet(viewsets.ModelViewSet):
    pagination_class = None
    serializer_class = IntegrationConnectionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return IntegrationConnection.objects.filter(owner=self.request.user)

    @action(detail=True, methods=["post"], url_path="test")
    def test_connection(self, request, pk=None):
        connection = self.get_object()
        try:
            result = provider_for_connection(connection).test_connection()
        except Exception as exc:
            connection.status = IntegrationConnection.Status.ERROR
            connection.last_error = str(exc)
            connection.last_tested_at = timezone.now()
            connection.save(update_fields=["status", "last_error", "last_tested_at", "updated_at"])
            return Response({"ok": False, "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        connection.status = IntegrationConnection.Status.CONNECTED
        connection.last_error = ""
        connection.last_tested_at = timezone.now()
        connection.save(update_fields=["status", "last_error", "last_tested_at", "updated_at"])
        return Response(result)


class LibraryIntegrationViewSet(viewsets.ModelViewSet):
    pagination_class = None
    serializer_class = LibraryIntegrationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = (
            LibraryIntegration.objects
            .filter(library__owner=self.request.user, connection__owner=self.request.user)
            .select_related("library", "connection")
        )
        library_id = self.request.query_params.get("library")
        if library_id:
            queryset = queryset.filter(library_id=library_id)
        return queryset


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def providers(request):
    return Response(provider_catalog())


def _target(library, target_type: str, target_id):
    if target_type == "channel":
        return get_object_or_404(Channel, id=target_id, library=library)
    if target_type == "online_video":
        return get_object_or_404(OnlineVideo, id=target_id, library=library)
    if target_type == "playlist":
        return get_object_or_404(Playlist, id=target_id, library=library)
    raise ValidationError({"target_type": "Unsupported integration lookup target."})


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def target_lookup(request, library_id, target_type, target_id):
    library = get_object_or_404(Library, id=library_id, owner=request.user)
    target = _target(library, target_type, target_id)
    source_id = str(getattr(target, "source_id", "") or "")
    if not source_id:
        raise ValidationError({"detail": "Target does not have a stable provider source ID."})
    return Response(
        {
            "target_type": target_type,
            "target_id": str(target.id),
            "source_id": source_id,
            "results": transient_lookup(
                library=library,
                target_type=target_type,
                source_id=source_id,
            ),
        }
    )


def _remote_image_response(*, artwork_url: str, provider, connection_provider: str):
    if not _allowed_artwork_url(
        artwork_url=artwork_url,
        provider=provider,
        connection_provider=connection_provider,
    ):
        return None

    headers = {"User-Agent": "LibraryForge/0.1"}

    if connection_provider == "tubearchivist":
        # Never leak the TA API token to a CDN/third-party URL found inside TA metadata.
        artwork_origin = urlparse(artwork_url)
        base_origin = urlparse(getattr(provider, "base_url", ""))
        if (artwork_origin.scheme, artwork_origin.netloc) == (base_origin.scheme, base_origin.netloc):
            headers.update(getattr(provider, "headers", {}))

    try:
        req = Request(artwork_url, headers=headers, method="GET")
        with urlopen(req, timeout=10) as response:
            body = response.read(MAX_REMOTE_ARTWORK_BYTES + 1)
            content_type = response.headers.get_content_type()
    except (HTTPError, URLError, TimeoutError, OSError):
        return None

    if len(body) > MAX_REMOTE_ARTWORK_BYTES:
        return None

    if not content_type.startswith("image/"):
        guessed = mimetypes.guess_type(artwork_url)[0] or ""
        if not guessed.startswith("image/"):
            return None
        content_type = guessed

    response = HttpResponse(body, content_type=content_type)
    response["Cache-Control"] = "private, max-age=3600"
    return response


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def library_artwork(request, library_id):
    library = get_object_or_404(Library, id=library_id, owner=request.user)
    target_type = str(request.query_params.get("target_type") or "")
    source_id = str(request.query_params.get("source_id") or "")

    if target_type not in {"channel", "online_video", "playlist"} or not source_id:
        raise Http404("Invalid integration artwork request.")

    for link in active_links_for_library(library=library, capability="artwork"):
        try:
            provider = provider_for_connection(link.connection)
            item = provider.lookup_one(target_type=target_type, source_id=source_id) or {}
            artwork_url = str(item.get("artwork_url") or "")
        except Exception:
            continue

        if not artwork_url:
            continue

        response = _remote_image_response(
            artwork_url=artwork_url,
            provider=provider,
            connection_provider=link.connection.provider,
        )
        if response is not None:
            return response

    raise Http404("No assigned integration returned artwork for this item.")
