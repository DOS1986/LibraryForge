import mimetypes
from pathlib import Path

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404

from rest_framework.decorators import (
    api_view,
    permission_classes,
)
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from catalog.models import ArtworkFile
from catalog.services.artwork import (
    scan_library_artwork,
    select_artwork,
)
from libraries.models import Library


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def artwork_content(
    request,
    artwork_id,
):
    artwork = get_object_or_404(
        ArtworkFile.objects.select_related(
            "library"
        ),
        id=artwork_id,
        library__owner=request.user,
        is_present=True,
    )

    root = Path(
        artwork.library.path
    ).resolve()

    try:
        file_path = (
            root
            / artwork.relative_path
        ).resolve(
            strict=True
        )

    except OSError as exc:
        raise Http404(
            "Artwork file is unavailable."
        ) from exc

    if (
        not file_path.is_file()
        or not file_path.is_relative_to(root)
    ):
        raise Http404(
            "Artwork file is unavailable."
        )

    content_type = (
        mimetypes.guess_type(
            file_path.name
        )[0]
        or "application/octet-stream"
    )

    if not content_type.startswith(
        "image/"
    ):
        raise Http404(
            "Artwork file is not an image."
        )

    return FileResponse(
        file_path.open("rb"),
        content_type=content_type,
        filename=file_path.name,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def artwork_select(
    request,
    artwork_id,
):
    artwork = get_object_or_404(
        ArtworkFile.objects.select_related(
            "library"
        ),
        id=artwork_id,
        library__owner=request.user,
    )

    try:
        result = select_artwork(
            artwork=artwork,
            user=request.user,
        )

    except ValueError as exc:
        raise ValidationError(
            {"detail": str(exc)}
        ) from exc

    return Response(result)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def library_artwork_refresh(
    request,
    library_id,
):
    library = get_object_or_404(
        Library,
        id=library_id,
        owner=request.user,
    )

    result = scan_library_artwork(
        library=library
    )

    return Response(result)
