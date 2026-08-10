from django.shortcuts import get_object_or_404

from rest_framework.decorators import (
    api_view,
    permission_classes,
)
from rest_framework.permissions import (
    IsAuthenticated,
)
from rest_framework.response import Response

from catalog.editor_serializers import (
    EpisodeMetadataEditSerializer,
    MediaVersionEditSerializer,
    MovieMetadataEditSerializer,
    SeasonMetadataEditSerializer,
    SeriesMetadataEditSerializer,
)
from catalog.models import (
    Episode,
    MediaVersion,
    Season,
    Series,
)
from catalog.services.canonical import (
    episode_detail,
    make_primary_version,
    movie_detail,
    season_detail,
    series_detail,
    update_episode_metadata,
    update_media_version,
    update_movie_metadata,
    update_season_metadata,
    update_series_metadata,
)
from media.models import MediaItem


def _payload_and_note(
    serializer,
):
    data = dict(
        serializer.validated_data
    )

    note = data.pop(
        "note",
        "",
    )

    return (
        data,
        note,
    )


@api_view(
    [
        "GET",
        "PATCH",
    ]
)
@permission_classes(
    [
        IsAuthenticated,
    ]
)
def movie_editor(
    request,
    item_id,
):
    item = get_object_or_404(
        MediaItem.objects.select_related(
            "library"
        ),
        id=item_id,
        library__owner=request.user,
        media_type=(
            MediaItem
            .MediaType
            .MOVIE
        ),
    )

    if request.method == "GET":
        return Response(
            movie_detail(
                item
            )
        )

    serializer = MovieMetadataEditSerializer(
        data=request.data,
        partial=True,
    )

    serializer.is_valid(
        raise_exception=True
    )

    values, note = _payload_and_note(
        serializer
    )

    return Response(
        update_movie_metadata(
            media_item=item,
            values=values,
            user=request.user,
            note=note,
        )
    )


@api_view(
    [
        "GET",
        "PATCH",
    ]
)
@permission_classes(
    [
        IsAuthenticated,
    ]
)
def series_editor(
    request,
    series_id,
):
    series = get_object_or_404(
        Series.objects.select_related(
            "library"
        ),
        id=series_id,
        library__owner=request.user,
    )

    if request.method == "GET":
        return Response(
            series_detail(
                series
            )
        )

    serializer = SeriesMetadataEditSerializer(
        instance=series,
        data=request.data,
        partial=True,
    )

    serializer.is_valid(
        raise_exception=True
    )

    values, note = _payload_and_note(
        serializer
    )

    return Response(
        update_series_metadata(
            series=series,
            values=values,
            user=request.user,
            note=note,
        )
    )


@api_view(
    [
        "GET",
        "PATCH",
    ]
)
@permission_classes(
    [
        IsAuthenticated,
    ]
)
def season_editor(
    request,
    season_id,
):
    season = get_object_or_404(
        Season.objects.select_related(
            "series",
            "series__library",
        ),
        id=season_id,
        series__library__owner=request.user,
    )

    if request.method == "GET":
        return Response(
            season_detail(
                season
            )
        )

    serializer = SeasonMetadataEditSerializer(
        data=request.data,
        partial=True,
    )

    serializer.is_valid(
        raise_exception=True
    )

    values, note = _payload_and_note(
        serializer
    )

    return Response(
        update_season_metadata(
            season=season,
            values=values,
            user=request.user,
            note=note,
        )
    )


@api_view(
    [
        "GET",
        "PATCH",
    ]
)
@permission_classes(
    [
        IsAuthenticated,
    ]
)
def episode_editor(
    request,
    episode_id,
):
    episode = get_object_or_404(
        Episode.objects.select_related(
            "media_item",
            "media_item__library",
            "season",
            "season__series",
        ),
        id=episode_id,
        media_item__library__owner=request.user,
    )

    if request.method == "GET":
        return Response(
            episode_detail(
                episode
            )
        )

    serializer = EpisodeMetadataEditSerializer(
        data=request.data,
        partial=True,
    )

    serializer.is_valid(
        raise_exception=True
    )

    values, note = _payload_and_note(
        serializer
    )

    return Response(
        update_episode_metadata(
            episode=episode,
            values=values,
            user=request.user,
            note=note,
        )
    )


@api_view(
    [
        "PATCH",
    ]
)
@permission_classes(
    [
        IsAuthenticated,
    ]
)
def media_version_editor(
    request,
    version_id,
):
    version = get_object_or_404(
        MediaVersion.objects.select_related(
            "media_item",
            "media_item__library",
            "media_file",
        ),
        id=version_id,
        media_item__library__owner=request.user,
    )

    serializer = MediaVersionEditSerializer(
        data=request.data,
        partial=True,
    )

    serializer.is_valid(
        raise_exception=True
    )

    values, note = _payload_and_note(
        serializer
    )

    return Response(
        update_media_version(
            version=version,
            values=values,
            user=request.user,
            note=note,
        )
    )


@api_view(
    [
        "POST",
    ]
)
@permission_classes(
    [
        IsAuthenticated,
    ]
)
def media_version_make_primary(
    request,
    version_id,
):
    version = get_object_or_404(
        MediaVersion.objects.select_related(
            "media_item",
            "media_item__library",
            "media_file",
        ),
        id=version_id,
        media_item__library__owner=request.user,
    )

    return Response(
        make_primary_version(
            version=version,
            user=request.user,
        )
    )
