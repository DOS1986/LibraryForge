import io

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APIClient

from catalog.models import (
    CanonicalFieldState,
    Channel,
    OnlineVideo,
    SemanticMatch,
)
from catalog.services.online_video import (
    online_video_semantic_key,
    resolve_online_video_file,
)
from libraries.models import Library
from media.models import MediaFile, MediaItem
from metadata.models import MetadataSource


pytestmark = pytest.mark.django_db


CHANNEL_ID = "UC1234567890123456789012"
VIDEO_ID = "abc123def45"
MANUAL_VIDEO_ID = "ZYX987wvu65"
SECOND_VIDEO_ID = "qwe987RTY65"
SECOND_CHANNEL_ID = "UC9876543210987654321098"


def make_library(suffix="attention"):
    user = get_user_model().objects.create_user(
        email=f"{suffix}@example.com",
        password="test-password",
    )
    library = Library.objects.create(
        owner=user,
        name=f"Online {suffix}",
        path=f"/library/{suffix}",
        content_type="online_video",
    )
    return user, library


def make_file(library, relative_path=f"{CHANNEL_ID}/{VIDEO_ID}.mp4"):
    item = MediaItem.objects.create(
        library=library,
        title="Temporary video",
    )
    media_file = MediaFile.objects.create(
        library=library,
        media_item=item,
        relative_path=relative_path,
        file_name=relative_path.rsplit("/", 1)[-1],
        extension="mp4",
        size_bytes=1000,
        duration_seconds=120,
        probe_status=MediaFile.ProbeStatus.OK,
        is_present=True,
    )
    return item, media_file


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_manual_online_video_resolution_creates_locked_identity():
    user, library = make_library("manual-online")
    item, media_file = make_file(
        library,
        relative_path="unknown/video.mp4",
    )
    match = SemanticMatch.objects.create(
        media_file=media_file,
        status=SemanticMatch.Status.UNRESOLVED,
        candidate_data={
            "kind": "online_video",
            "reason": "stable_source_identity_missing",
        },
    )

    response = client_for(user).post(
        f"/api/semantic-matches/{match.id}/resolve/",
        {
            "candidate_source": "manual",
            "kind": "online_video",
            "provider": "youtube",
            "video_id": MANUAL_VIDEO_ID,
            "title": "Corrected Video",
            "channel_id": CHANNEL_ID,
            "channel_title": "Corrected Channel",
            "channel_handle": "@corrected",
            "video_kind": "video",
            "lock": True,
            "notes": "Confirmed from the original archive record.",
        },
        format="json",
    )

    assert response.status_code == 200, response.data

    match.refresh_from_db()
    item.refresh_from_db()
    video = OnlineVideo.objects.get(media_item=item)
    channel = Channel.objects.get(id=video.channel_id)

    assert match.status == SemanticMatch.Status.MANUAL
    assert match.source == SemanticMatch.Source.MANUAL
    assert match.locked is True
    assert item.semantic_locked is True
    assert item.semantic_key == online_video_semantic_key(
        "youtube",
        MANUAL_VIDEO_ID,
    )
    assert item.title == "Corrected Video"
    assert video.provider == "youtube"
    assert video.source_id == MANUAL_VIDEO_ID
    assert video.locked is True
    assert channel.source_id == CHANNEL_ID
    assert channel.title == "Corrected Channel"

    title_state = CanonicalFieldState.objects.get(
        target_type=CanonicalFieldState.TargetType.MEDIA_ITEM,
        target_id=item.id,
        field_name="title",
    )
    assert title_state.source == CanonicalFieldState.Source.MANUAL
    assert title_state.locked is True


def test_online_video_source_candidate_can_be_confirmed():
    user, library = make_library("source-candidate")
    _item, media_file = make_file(library)
    match = SemanticMatch.objects.create(
        media_file=media_file,
        status=SemanticMatch.Status.CONFLICT,
        candidate_data={
            "kind": "online_video",
            "reason": "source_identity_disagreement",
            "sources": {
                "tubearchivist_path": {
                    "source_type": "tubearchivist_path",
                    "source_ref": "tubearchivist-path:test",
                    "provider": "youtube",
                    "video": {
                        "id": VIDEO_ID,
                        "title": "Path Video",
                    },
                    "channel": {
                        "id": CHANNEL_ID,
                        "title": "Path Channel",
                    },
                    "playlists": [],
                }
            },
        },
    )

    response = client_for(user).post(
        f"/api/semantic-matches/{match.id}/resolve/",
        {
            "candidate_source": "tubearchivist_path",
            "lock": True,
        },
        format="json",
    )

    assert response.status_code == 200, response.data
    match.refresh_from_db()
    assert match.status == SemanticMatch.Status.MANUAL
    assert match.locked is True
    assert OnlineVideo.objects.get(
        media_item=media_file.media_item
    ).source_id == VIDEO_ID


def test_unlock_updates_online_video_lock_state():
    user, library = make_library("unlock-online")
    item, media_file = make_file(library, relative_path="unknown/video.mp4")
    match = SemanticMatch.objects.create(
        media_file=media_file,
        status=SemanticMatch.Status.UNRESOLVED,
        candidate_data={"kind": "online_video"},
    )

    client = client_for(user)
    resolved = client.post(
        f"/api/semantic-matches/{match.id}/resolve/",
        {
            "candidate_source": "manual",
            "kind": "online_video",
            "provider": "youtube",
            "video_id": MANUAL_VIDEO_ID,
            "lock": True,
        },
        format="json",
    )
    assert resolved.status_code == 200, resolved.data

    response = client.post(
        f"/api/semantic-matches/{match.id}/set-lock/",
        {"locked": False},
        format="json",
    )
    assert response.status_code == 200, response.data

    match.refresh_from_db()
    item.refresh_from_db()
    video = OnlineVideo.objects.get(media_item=item)
    assert match.locked is False
    assert item.semantic_locked is False
    assert video.locked is False


def test_reset_online_video_returns_to_automatic_path_identity():
    user, library = make_library("reset-online")
    item, media_file = make_file(library)
    match = SemanticMatch.objects.create(
        media_file=media_file,
        status=SemanticMatch.Status.UNRESOLVED,
        candidate_data={"kind": "online_video"},
    )

    client = client_for(user)
    manual = client.post(
        f"/api/semantic-matches/{match.id}/resolve/",
        {
            "candidate_source": "manual",
            "kind": "online_video",
            "provider": "youtube",
            "video_id": MANUAL_VIDEO_ID,
            "lock": True,
        },
        format="json",
    )
    assert manual.status_code == 200, manual.data

    reset = client.post(
        f"/api/semantic-matches/{match.id}/reset/",
        {},
        format="json",
    )
    assert reset.status_code == 200, reset.data

    item.refresh_from_db()
    match.refresh_from_db()
    video = OnlineVideo.objects.get(media_item=item)

    assert reset.data["result"] == "matched"
    assert match.status == SemanticMatch.Status.MATCHED
    assert match.locked is False
    assert video.source_id == VIDEO_ID
    assert item.semantic_key == online_video_semantic_key("youtube", VIDEO_ID)


def test_online_video_provenance_endpoint_exposes_sources_and_field_states():
    user, library = make_library("provenance-online")
    item, media_file = make_file(library)

    MetadataSource.objects.create(
        media_item=item,
        media_file=media_file,
        source_type=MetadataSource.SourceType.EMBEDDED,
        status=MetadataSource.Status.DETECTED,
        extracted_data={"title": "Embedded Title"},
        raw_data={"format_tags": {"title": "Embedded Title"}},
    )

    match = SemanticMatch.objects.create(
        media_file=media_file,
        status=SemanticMatch.Status.UNRESOLVED,
        candidate_data={"kind": "online_video"},
    )

    response = client_for(user).get(
        f"/api/semantic-matches/{match.id}/provenance/"
    )

    assert response.status_code == 200, response.data
    assert response.data["file"]["relative_path"] == media_file.relative_path
    assert len(response.data["metadata_sources"]) == 1
    assert response.data["metadata_sources"][0]["source_type"] == "embedded"
    assert "media_item" in response.data["field_states"]


def test_rebuild_semantic_catalog_all_includes_online_video():
    _user, library = make_library("command-online")
    _item, _media_file = make_file(library)

    stdout = io.StringIO()
    call_command("rebuild_semantic_catalog", "--all", stdout=stdout)

    output = stdout.getvalue()
    assert library.name in output
    assert "matched=1" in output


def test_manual_channel_reassignment_does_not_mutate_shared_channel():
    user, library = make_library("shared-channel")
    first_item, first_file = make_file(
        library,
        relative_path=f"{CHANNEL_ID}/{VIDEO_ID}.mp4",
    )
    second_item, second_file = make_file(
        library,
        relative_path=f"{CHANNEL_ID}/{SECOND_VIDEO_ID}.mp4",
    )

    assert resolve_online_video_file(library=library, media_file=first_file) == "matched"
    assert resolve_online_video_file(library=library, media_file=second_file) == "matched"

    original_channel = Channel.objects.get(
        library=library,
        provider="youtube",
        source_id=CHANNEL_ID,
    )
    original_channel.title = "Shared Channel"
    original_channel.save(update_fields=["title", "updated_at"])

    first_match = SemanticMatch.objects.get(media_file=first_file)
    response = client_for(user).post(
        f"/api/semantic-matches/{first_match.id}/resolve/",
        {
            "candidate_source": "manual",
            "kind": "online_video",
            "provider": "youtube",
            "video_id": VIDEO_ID,
            "channel_id": SECOND_CHANNEL_ID,
            "channel_title": "Corrected Channel",
            "lock": True,
        },
        format="json",
    )

    assert response.status_code == 200, response.data

    original_channel.refresh_from_db()
    first_video = OnlineVideo.objects.select_related("channel").get(
        media_item=first_item
    )
    second_video = OnlineVideo.objects.select_related("channel").get(
        media_item=second_item
    )

    assert original_channel.source_id == CHANNEL_ID
    assert original_channel.title == "Shared Channel"
    assert second_video.channel_id == original_channel.id
    assert second_video.channel.source_id == CHANNEL_ID
    assert first_video.channel_id != original_channel.id
    assert first_video.channel.source_id == SECOND_CHANNEL_ID
    assert first_video.channel.title == "Corrected Channel"


def test_confirming_detected_source_identity_does_not_overwrite_canonical_title():
    user, library = make_library("identity-only")
    item, media_file = make_file(library)
    item.title = "User-visible canonical title"
    item.save(update_fields=["title", "updated_at"])

    match = SemanticMatch.objects.create(
        media_file=media_file,
        status=SemanticMatch.Status.CONFLICT,
        candidate_data={
            "kind": "online_video",
            "reason": "source_identity_disagreement",
            "sources": {
                "tubearchivist_path": {
                    "source_type": "tubearchivist_path",
                    "source_ref": "tubearchivist-path:identity-only",
                    "provider": "youtube",
                    "video": {
                        "id": VIDEO_ID,
                        "title": "Different source title",
                    },
                    "channel": {
                        "id": CHANNEL_ID,
                        "title": "Source Channel Title",
                    },
                    "playlists": [],
                }
            },
        },
    )

    response = client_for(user).post(
        f"/api/semantic-matches/{match.id}/resolve/",
        {
            "candidate_source": "tubearchivist_path",
            "lock": True,
        },
        format="json",
    )

    assert response.status_code == 200, response.data
    item.refresh_from_db()

    assert item.title == "User-visible canonical title"
    assert not CanonicalFieldState.objects.filter(
        target_type=CanonicalFieldState.TargetType.MEDIA_ITEM,
        target_id=item.id,
        field_name="title",
        source=CanonicalFieldState.Source.MANUAL,
        source_ref="semantic-remediation",
    ).exists()
