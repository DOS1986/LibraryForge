"""Read-only metadata-provider match endpoints for movies and series.

GET only: these endpoints retrieve and compare provider data and never change
catalog metadata, provenance, or history.
"""

from __future__ import annotations

from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from metadata.providers.types import MetadataProviderError
from metadata.services.provider_match import (
    ERROR_STATUS,
    MatchRequestError,
    build_preview,
    error_payload,
    match_context,
    resolve_target,
    search_candidates,
)


class MetadataProviderThrottle(UserRateThrottle):
    """Per-user budget for requests that may call an external metadata provider.

    The rate comes from ``REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["metadata_provider"]``
    (env ``LIBRARYFORGE_METADATA_PROVIDER_RATE``).
    """

    scope = "metadata_provider"


def _provider_error_response(error: MetadataProviderError) -> Response:
    status = ERROR_STATUS.get(error.category, 502)
    response = Response(error_payload(error), status=status)
    if error.retry_after_seconds is not None:
        response["Retry-After"] = str(error.retry_after_seconds)
    return response


def _run(callable_):
    try:
        return Response(callable_())
    except MatchRequestError as error:
        return Response({"detail": error.message}, status=error.status)
    except MetadataProviderError as error:
        return _provider_error_response(error)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def match_context_view(request, target_type, target_id):
    resolved = resolve_target(user=request.user, target_type=target_type, target_id=target_id)
    return Response(match_context(resolved))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@throttle_classes([MetadataProviderThrottle])
def match_search_view(request, target_type, target_id):
    resolved = resolve_target(user=request.user, target_type=target_type, target_id=target_id)
    params = request.query_params
    return _run(
        lambda: search_candidates(
            resolved,
            connection_id=params.get("connection"),
            query=params.get("query"),
            year=params.get("year"),
            page=params.get("page"),
            language=params.get("language"),
        )
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@throttle_classes([MetadataProviderThrottle])
def match_preview_view(request, target_type, target_id):
    resolved = resolve_target(user=request.user, target_type=target_type, target_id=target_id)
    params = request.query_params
    return _run(
        lambda: build_preview(
            resolved,
            connection_id=params.get("connection"),
            source_id=(params.get("source_id") or "").strip(),
            language=params.get("language"),
            territory=params.get("territory"),
        )
    )
