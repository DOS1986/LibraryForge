import mimetypes
import subprocess
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.decorators import (
    api_view,
    permission_classes,
)
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from catalog.models import ArtworkFile
from catalog.services.artwork import (
    embedded_artwork_locator,
    scan_library_artwork,
    select_artwork,
    serialize_artwork,
)
from libraries.models import Library
from libraries.services.storage import StorageAccessError
from media.models import MediaFile


MAX_EMBEDDED_ARTWORK_BYTES = 25 * 1024 * 1024


def _library_file_path(*, library, relative_path: str):
    root = Path(library.path).resolve()
    try:
        file_path = (
            root
            / relative_path
        ).resolve(strict=True)
    except OSError as exc:
        raise Http404(
            "Artwork source file is unavailable."
        ) from exc

    if (
        not file_path.is_file()
        or not file_path.is_relative_to(root)
    ):
        raise Http404(
            "Artwork source file is unavailable."
        )

    return file_path


def _attached_picture_stream(media_file: MediaFile, stream_index: int):
    streams = (media_file.raw_probe or {}).get("streams") or []

    for stream in streams:
        if not isinstance(stream, dict):
            continue

        try:
            index = int(stream.get("index"))
        except (TypeError, ValueError):
            continue

        if index != stream_index:
            continue

        disposition = stream.get("disposition") or {}

        if disposition.get("attached_pic") in (1, "1", True):
            return stream

    return None


def _ffmpeg_executable():
    configured = getattr(settings, "FFMPEG_PATH", "")

    if configured:
        return str(configured)

    ffprobe = str(getattr(settings, "FFPROBE_PATH", "ffprobe"))
    ffprobe_path = Path(ffprobe)

    if ffprobe_path.name.casefold() in {"ffprobe", "ffprobe.exe"}:
        suffix = ".exe" if ffprobe_path.suffix.casefold() == ".exe" else ""
        sibling = ffprobe_path.with_name(f"ffmpeg{suffix}")

        if ffprobe_path.parent != Path(".") and sibling.exists():
            return str(sibling)

    return "ffmpeg"


def _embedded_artwork_response(artwork: ArtworkFile):
    locator = embedded_artwork_locator(artwork.relative_path)

    if locator is None:
        raise Http404("Embedded artwork locator is invalid.")

    media_file_id, stream_index = locator

    media_file = get_object_or_404(
        MediaFile,
        id=media_file_id,
        library=artwork.library,
        is_present=True,
    )

    if _attached_picture_stream(media_file, stream_index) is None:
        raise Http404("Embedded artwork stream is unavailable.")

    file_path = _library_file_path(
        library=artwork.library,
        relative_path=media_file.relative_path,
    )

    command = [
        _ffmpeg_executable(),
        "-v",
        "error",
        "-i",
        str(file_path),
        "-map",
        f"0:{stream_index}",
        "-frames:v",
        "1",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "pipe:1",
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            timeout=15,
        )

    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Http404(
            "Unable to read embedded artwork."
        ) from exc

    if result.returncode != 0 or not result.stdout:
        raise Http404("Unable to read embedded artwork.")

    if len(result.stdout) > MAX_EMBEDDED_ARTWORK_BYTES:
        raise Http404("Embedded artwork is unexpectedly large.")

    response = HttpResponse(
        result.stdout,
        content_type="image/png",
    )
    response["Cache-Control"] = "private, max-age=3600"

    return response


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

    if embedded_artwork_locator(artwork.relative_path) is not None:
        return _embedded_artwork_response(artwork)

    file_path = _library_file_path(
        library=artwork.library,
        relative_path=artwork.relative_path,
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

    try:
        result = scan_library_artwork(
            library=library
        )

    except StorageAccessError as exc:
        return Response(
            {
                "detail": str(exc)
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response(result)