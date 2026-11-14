"""Library content-rating coverage and reviewed rating suggestions.

Both endpoints are GET only and never change catalog data. Suggested ratings
are applied through the metadata-match apply endpoint, one confirmed item at
a time.
"""

from __future__ import annotations

from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated

from metadata.match_views import MetadataProviderThrottle, _run
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
