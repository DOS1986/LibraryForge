"""Library content-rating coverage and reviewed rating suggestions.

Both endpoints are GET only and never change catalog data. Suggested ratings
are applied through the metadata-match apply endpoint, one confirmed item at
a time.
"""

from __future__ import annotations

from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated

from metadata.match_views import MetadataProviderThrottle, _run
from metadata.services.nfo_ratings import apply_nfo_import, preview_nfo_import
from metadata.services.ratings import owned_library, rating_coverage, rating_suggestions


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def library_ratings_view(request, library_id):
    library = owned_library(user=request.user, library_id=library_id)
    params = request.query_params
    return _run(
        lambda: rating_coverage(
            library,
            kind=params.get("kind") or "movie",
            status=params.get("status"),
            search=params.get("search"),
            page=params.get("page"),
            page_size=params.get("page_size"),
        )
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@throttle_classes([MetadataProviderThrottle])
def library_rating_suggestions_view(request, library_id):
    library = owned_library(user=request.user, library_id=library_id)
    params = request.query_params
    return _run(
        lambda: rating_suggestions(
            library,
            user=request.user,
            kind=params.get("kind") or "movie",
            ids=(params.get("ids") or "").split(","),
            connection_id=params.get("connection"),
        )
    )


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def library_nfo_rating_import_view(request, library_id):
    """GET previews importing ratings from indexed NFO files; POST applies it.

    No filesystem access: this reads NFO data LibraryForge has already
    indexed, so it works for read-only libraries. The plan is recomputed when
    applying, and only empty or NFO-sourced ratings are written.
    """

    library = owned_library(user=request.user, library_id=library_id)
    if request.method == "GET":
        return _run(lambda: preview_nfo_import(library, kind=request.query_params.get("kind") or "movie"))
    return _run(lambda: apply_nfo_import(library, kind=str(request.data.get("kind") or "movie"), user=request.user))
