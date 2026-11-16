"""Jellyfin server endpoints: library links, rescans, and the parental report.

All endpoints are owner-scoped. Reading Jellyfin's library list and user
settings never changes anything; a rescan asks Jellyfin to scan one library
for new and changed files and never changes LibraryForge data.
"""

from __future__ import annotations

import re
from pathlib import PureWindowsPath

from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from integrations.models import IntegrationConnection, LibraryIntegration
from integrations.providers.base import CAPABILITY_OUTPUT
from integrations.services import provider_for_connection
from metadata.match_views import _provider_error_response
from metadata.providers.types import MetadataProviderError

OPTION_LIBRARY_ID = "jellyfin_library_id"


def _link(user, link_id) -> LibraryIntegration:
    return get_object_or_404(
        LibraryIntegration.objects.select_related("library", "connection"),
        id=link_id,
        library__owner=user,
        connection__owner=user,
        connection__provider="jellyfin",
    )


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").casefold())


def _last_segment(path: str) -> str:
    # Handles both Jellyfin (Linux) paths and LibraryForge (often UNC) paths.
    return PureWindowsPath(str(path).replace("/", "\\").rstrip("\\")).name


def suggest_library(link: LibraryIntegration, libraries: list[dict]) -> str | None:
    """Best guess at the Jellyfin library for a LibraryForge library.

    Folder names usually differ only in their parent paths (a UNC share in
    LibraryForge, a container mount in Jellyfin), so the last folder name is
    compared first, then the library name.
    """

    folder = _key(_last_segment(link.library.path))
    name = _key(link.library.name)
    for library in libraries:
        if folder and any(_key(_last_segment(location)) == folder for location in library["locations"]):
            return library["id"]
    for library in libraries:
        if name and _key(library["name"]) in {name, folder}:
            return library["id"]
    return None


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def jellyfin_link_view(request, link_id):
    """GET: Jellyfin's libraries with the current and suggested link.
    POST {"jellyfin_library_id": "..."}: save the link ("" clears it)."""

    link = _link(request.user, link_id)
    provider = provider_for_connection(link.connection)
    try:
        libraries = provider.libraries()
    except MetadataProviderError as error:
        return _provider_error_response(error)

    if request.method == "POST":
        chosen = str(request.data.get(OPTION_LIBRARY_ID) or "").strip()
        if chosen and chosen not in {library["id"] for library in libraries}:
            return Response({"detail": "Choose one of this Jellyfin server's libraries."}, status=400)
        options = dict(link.options or {})
        if chosen:
            options[OPTION_LIBRARY_ID] = chosen
        else:
            options.pop(OPTION_LIBRARY_ID, None)
        link.options = options
        link.save(update_fields=["options", "updated_at"])

    return Response(
        {
            "link_id": str(link.id),
            "libraries": libraries,
            "selected_id": (link.options or {}).get(OPTION_LIBRARY_ID),
            "suggested_id": suggest_library(link, libraries),
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def jellyfin_refresh_view(request, link_id):
    """Ask Jellyfin to scan the linked library for new and changed files."""

    link = _link(request.user, link_id)
    if not link.enabled or not link.connection.enabled or CAPABILITY_OUTPUT not in (link.capabilities or []):
        return Response(
            {"detail": "Enable this Jellyfin connection for the library, with the output capability, first."},
            status=400,
        )
    library_id = (link.options or {}).get(OPTION_LIBRARY_ID)
    if not library_id:
        return Response({"detail": "Choose which Jellyfin library this is in Library Settings first."}, status=400)
    try:
        provider_for_connection(link.connection).refresh_library(library_id)
    except MetadataProviderError as error:
        return _provider_error_response(error)
    return Response({"ok": True, "detail": "Jellyfin started scanning the library for changes."})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def jellyfin_parental_view(request, connection_id):
    """Each Jellyfin user's parental controls and what they can see."""

    connection = get_object_or_404(
        IntegrationConnection, id=connection_id, owner=request.user, provider="jellyfin"
    )
    try:
        report = provider_for_connection(connection).parental_report()
    except MetadataProviderError as error:
        return _provider_error_response(error)
    return Response({"connection_id": str(connection.id), **report})
