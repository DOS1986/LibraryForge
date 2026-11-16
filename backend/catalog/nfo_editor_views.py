"""Editors for online videos and channels, and NFO field sync for catalog items."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from catalog.models import Channel, OnlineVideo
from catalog.services.online_video_editor import (
    channel_detail,
    online_video_detail,
    update_channel,
    update_online_video,
)
from metadata.match_views import _run
from metadata.services.nfo_fields import (
    create_missing_nfos,
    nfo_comparison,
    preview_missing_nfos,
    resolve,
    write_fields,
)
from metadata.services.provider_match import MatchRequestError
from metadata.services.ratings import owned_library

_KINDS = {"movies": "movie", "series": "series", "episodes": "episode"}


def _values_and_note(request) -> tuple[dict, str]:
    if not isinstance(request.data, dict):
        raise MatchRequestError("Send the changes as an object.")
    values = dict(request.data)
    note = values.pop("note", "")
    return values, str(note or "")[:500]


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def online_video_editor(request, video_id):
    video = get_object_or_404(
        OnlineVideo.objects.select_related("media_item", "channel", "library"), id=video_id, library__owner=request.user
    )
    if request.method == "GET":
        return _run(lambda: online_video_detail(video))

    def save():
        values, note = _values_and_note(request)
        return update_online_video(video=video, values=values, user=request.user, note=note)

    return _run(save)


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def channel_editor(request, channel_id):
    channel = get_object_or_404(Channel.objects.select_related("library"), id=channel_id, library__owner=request.user)
    if request.method == "GET":
        return _run(lambda: channel_detail(channel))

    def save():
        values, note = _values_and_note(request)
        return update_channel(channel=channel, values=values, user=request.user, note=note)

    return _run(save)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def item_nfo_view(request, kind, item_id):
    """GET compares LibraryForge's fields with the item's NFO; POST writes the
    chosen fields (body: ``fields``, a list of NFO tags, or omit for every
    field that differs), creating the NFO if there isn't one."""

    if kind not in _KINDS:
        def refuse():
            raise MatchRequestError("Kind must be movies, series, or episodes.")

        return _run(refuse)
    target = resolve(user=request.user, kind=_KINDS[kind], item_id=item_id)
    if request.method == "GET":
        return _run(lambda: nfo_comparison(target))

    def save():
        fields = request.data.get("fields") if isinstance(request.data, dict) else None
        if fields is not None and (not isinstance(fields, list) or not all(isinstance(item, str) for item in fields)):
            raise MatchRequestError("Fields must be a list of NFO tags.")
        result = write_fields(target, tags=fields)
        return {**result, "comparison": nfo_comparison(target)}

    return _run(save)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def library_nfo_create_view(request, library_id):
    """GET previews creating NFOs for movies or series that have none; POST
    creates one batch (``kind``, optional ``cursor`` and ``batch``)."""

    library = owned_library(user=request.user, library_id=library_id)
    if request.method == "GET":
        return _run(lambda: preview_missing_nfos(library, kind=request.query_params.get("kind") or "movie"))
    return _run(
        lambda: create_missing_nfos(
            library,
            kind=str(request.data.get("kind") or "movie"),
            cursor=request.data.get("cursor") or None,
            batch=request.data.get("batch"),
        )
    )
