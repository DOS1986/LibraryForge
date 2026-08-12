from __future__ import annotations

from catalog.models import (
    CanonicalFieldState,
    OnlineVideo,
    PlaylistMembership,
)
from catalog.services.canonical import serialize_field_states
from metadata.models import MetadataSource


def _metadata_source_rows(media_item):
    return [
        {
            "id": str(source.id),
            "source_type": source.source_type,
            "source_type_label": source.get_source_type_display(),
            "status": source.status,
            "status_label": source.get_status_display(),
            "media_file_id": str(source.media_file_id),
            "file_name": source.media_file.file_name,
            "relative_path": source.media_file.relative_path,
            "extracted_data": source.extracted_data,
            "error": source.error,
            "last_checked_at": source.last_checked_at,
        }
        for source in (
            MetadataSource.objects
            .filter(media_item=media_item)
            .select_related("media_file")
            .order_by("source_type", "media_file__relative_path")
        )
    ]


def semantic_match_provenance(match):
    media_file = match.media_file
    media_item = media_file.media_item

    field_states = {
        "media_item": serialize_field_states(
            target_type=CanonicalFieldState.TargetType.MEDIA_ITEM,
            target_id=media_item.id,
        ),
    }

    current_identity = None
    playlist_memberships = []

    online_video = (
        OnlineVideo.objects
        .filter(media_item=media_item)
        .select_related("channel")
        .first()
    )

    if online_video:
        field_states["online_video"] = serialize_field_states(
            target_type=CanonicalFieldState.TargetType.ONLINE_VIDEO,
            target_id=online_video.id,
        )

        if online_video.channel_id:
            field_states["channel"] = serialize_field_states(
                target_type=CanonicalFieldState.TargetType.CHANNEL,
                target_id=online_video.channel_id,
            )
        else:
            field_states["channel"] = []

        current_identity = {
            "kind": "online_video",
            "provider": online_video.provider,
            "source_id": online_video.source_id,
            "semantic_key": media_item.semantic_key,
            "channel": (
                {
                    "id": str(online_video.channel_id),
                    "provider": online_video.channel.provider,
                    "source_id": online_video.channel.source_id,
                    "title": online_video.channel.title,
                    "handle": online_video.channel.handle,
                }
                if online_video.channel_id
                else None
            ),
        }

        playlist_memberships = [
            {
                "id": str(membership.id),
                "position": membership.position,
                "metadata": membership.metadata,
                "playlist": {
                    "id": str(membership.playlist_id),
                    "provider": membership.playlist.provider,
                    "source_id": membership.playlist.source_id,
                    "title": membership.playlist.title,
                },
            }
            for membership in (
                PlaylistMembership.objects
                .filter(online_video=online_video)
                .select_related("playlist")
                .order_by("playlist__title", "position")
            )
        ]

    if current_identity is None and media_item.semantic_key:
        current_identity = {
            "kind": media_item.media_type,
            "title": media_item.title,
            "semantic_key": media_item.semantic_key,
        }

    return {
        "match": {
            "id": str(match.id),
            "status": match.status,
            "status_label": match.get_status_display(),
            "source": match.source,
            "source_label": match.get_source_display() if match.source else "",
            "confidence": match.confidence,
            "locked": match.locked,
            "notes": match.notes,
            "last_resolved_at": match.last_resolved_at,
        },
        "file": {
            "id": str(media_file.id),
            "file_name": media_file.file_name,
            "relative_path": media_file.relative_path,
        },
        "current_identity": current_identity,
        "field_states": field_states,
        "metadata_sources": _metadata_source_rows(media_item),
        "playlist_memberships": playlist_memberships,
        "candidate_data": match.candidate_data or {},
    }
