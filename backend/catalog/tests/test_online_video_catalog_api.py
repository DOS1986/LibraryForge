from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.models import (
    Channel,
    MediaVersion,
    OnlineVideo,
    Playlist,
    PlaylistMembership,
)
from libraries.models import Library
from media.models import MediaFile, MediaItem


pytestmark = pytest.mark.django_db


def make_library(suffix: str, *, owner=None):
    owner = owner or get_user_model().objects.create_user(
        email=f"catalog-{suffix}@example.com",
        password="test-password",
    )
    library = Library.objects.create(
        owner=owner,
        name=f"Online {suffix}",
        path=f"/library/online-{suffix}",
        content_type="online_video",
    )
    return owner, library


def make_channel(library, source_id, title):
    return Channel.objects.create(
        library=library,
        provider="youtube",
        source_id=source_id,
        semantic_key=f"channel:youtube:{source_id}",
        title=title,
        sort_title=title,
        handle=f"@{title.lower().replace(' ', '')}",
        source_url=f"https://www.youtube.com/channel/{source_id}",
    )


def make_video(
    library,
    channel,
    source_id,
    title,
    *,
    upload_date,
    size_bytes,
    duration_seconds,
    present=True,
):
    item = MediaItem.objects.create(
        library=library,
        title=title,
        description=f"Description for {title}",
        release_date=upload_date,
        media_type=MediaItem.MediaType.ONLINE_VIDEO,
        semantic_key=f"online-video:youtube:{source_id}",
    )
    media_file = MediaFile.objects.create(
        library=library,
        media_item=item,
        relative_path=f"{channel.source_id}/{source_id}.mp4",
        file_name=f"{source_id}.mp4",
        extension="mp4",
        size_bytes=size_bytes,
        duration_seconds=duration_seconds,
        probe_status=MediaFile.ProbeStatus.OK,
        is_present=present,
    )
    MediaVersion.objects.create(
        media_item=item,
        media_file=media_file,
        name="Default",
        is_primary=True,
    )
    return OnlineVideo.objects.create(
        library=library,
        media_item=item,
        channel=channel,
        provider="youtube",
        source_id=source_id,
        source_url=f"https://www.youtube.com/watch?v={source_id}",
        upload_date=upload_date,
        video_kind=OnlineVideo.VideoKind.VIDEO,
        tags=["libraryforge"],
        categories=["Technology"],
        external_ids={"youtube": source_id},
    )


def make_playlist(library, channel, source_id, title):
    return Playlist.objects.create(
        library=library,
        channel=channel,
        provider="youtube",
        source_id=source_id,
        semantic_key=f"playlist:youtube:{source_id}",
        title=title,
        playlist_kind=Playlist.PlaylistKind.REMOTE,
    )


def authenticated_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def response_results(response):
    if isinstance(response.data, dict) and "results" in response.data:
        return response.data["results"]
    return response.data


def test_channel_catalog_returns_present_video_aggregates_only():
    user, library = make_library("channels")
    channel = make_channel(
        library,
        "UChYpy_1syqfkN-x1wLkecAw",
        "Example Channel",
    )

    make_video(
        library,
        channel,
        "UK4X75tY6_k",
        "First Video",
        upload_date=date(2026, 7, 15),
        size_bytes=1000,
        duration_seconds=120,
    )
    make_video(
        library,
        channel,
        "abcdefghijk",
        "Second Video",
        upload_date=date(2026, 7, 20),
        size_bytes=2000,
        duration_seconds=180,
    )
    make_video(
        library,
        channel,
        "zzzzzzzzzzz",
        "Missing Video",
        upload_date=date(2026, 7, 25),
        size_bytes=9999,
        duration_seconds=999,
        present=False,
    )

    client = authenticated_client(user)
    response = client.get(
        reverse("catalog-channel-list"),
        {"library": str(library.id)},
    )

    assert response.status_code == 200
    results = response_results(response)
    assert len(results) == 1

    row = results[0]
    assert row["title"] == "Example Channel"
    assert row["source_id"] == "UChYpy_1syqfkN-x1wLkecAw"
    assert row["video_count"] == 2
    assert row["runtime_seconds"] == pytest.approx(300)
    assert row["storage_bytes"] == 3000
    assert str(row["last_upload_date"]) == "2026-07-20"


def test_online_video_catalog_exposes_channel_versions_and_playlists():
    user, library = make_library("videos")
    channel = make_channel(
        library,
        "UC1234567890123456789012",
        "Technology Channel",
    )
    video = make_video(
        library,
        channel,
        "abc123def45",
        "Building a Home Server",
        upload_date=date(2026, 8, 1),
        size_bytes=4096,
        duration_seconds=321,
    )
    playlist = make_playlist(
        library,
        channel,
        "PL12345678901234567890123456789012",
        "Home Lab",
    )
    PlaylistMembership.objects.create(
        playlist=playlist,
        online_video=video,
        position=4,
    )

    client = authenticated_client(user)
    response = client.get(
        reverse("catalog-online-video-list"),
        {
            "library": str(library.id),
            "channel": str(channel.id),
        },
    )

    assert response.status_code == 200
    results = response_results(response)
    assert len(results) == 1

    row = results[0]
    assert row["title"] == "Building a Home Server"
    assert row["channel_id"] == str(channel.id)
    assert row["channel_title"] == "Technology Channel"
    assert row["source_id"] == "abc123def45"
    assert row["runtime_seconds"] == pytest.approx(321)
    assert row["storage_bytes"] == 4096
    assert row["version_count"] == 1
    assert row["playlist_count"] == 1
    assert row["versions"][0]["file_name"] == "abc123def45.mp4"
    assert row["playlists"][0]["position"] == 4
    assert row["playlists"][0]["playlist"]["title"] == "Home Lab"


def test_online_video_catalog_filters_by_playlist_kind_and_upload_date():
    user, library = make_library("filters")
    channel = make_channel(
        library,
        "UC9876543210987654321098",
        "Filter Channel",
    )
    older = make_video(
        library,
        channel,
        "older123456",
        "Older Video",
        upload_date=date(2026, 6, 1),
        size_bytes=100,
        duration_seconds=10,
    )
    newer = make_video(
        library,
        channel,
        "newer123456",
        "Newer Video",
        upload_date=date(2026, 8, 1),
        size_bytes=200,
        duration_seconds=20,
    )
    newer.video_kind = OnlineVideo.VideoKind.SHORT
    newer.save(update_fields=["video_kind", "updated_at"])

    playlist = make_playlist(
        library,
        channel,
        "PLFILTER123456789012345678901234",
        "Filtered Playlist",
    )
    PlaylistMembership.objects.create(
        playlist=playlist,
        online_video=newer,
        position=1,
    )
    PlaylistMembership.objects.create(
        playlist=playlist,
        online_video=older,
        position=2,
    )

    client = authenticated_client(user)
    response = client.get(
        reverse("catalog-online-video-list"),
        {
            "library": str(library.id),
            "playlist": str(playlist.id),
            "kind": OnlineVideo.VideoKind.SHORT,
            "uploaded_after": "2026-07-01",
        },
    )

    assert response.status_code == 200
    results = response_results(response)
    assert [row["title"] for row in results] == ["Newer Video"]


def test_playlist_catalog_returns_channel_and_aggregates():
    user, library = make_library("playlists")
    channel = make_channel(
        library,
        "UC5555555555555555555555",
        "Playlist Channel",
    )
    first = make_video(
        library,
        channel,
        "first123456",
        "First",
        upload_date=date(2026, 7, 1),
        size_bytes=1000,
        duration_seconds=100,
    )
    second = make_video(
        library,
        channel,
        "second12345",
        "Second",
        upload_date=date(2026, 7, 2),
        size_bytes=2500,
        duration_seconds=250,
    )
    playlist = make_playlist(
        library,
        channel,
        "PL55555555555555555555555555555555",
        "My Playlist",
    )
    PlaylistMembership.objects.create(
        playlist=playlist,
        online_video=first,
        position=1,
    )
    PlaylistMembership.objects.create(
        playlist=playlist,
        online_video=second,
        position=2,
    )

    client = authenticated_client(user)
    response = client.get(
        reverse("catalog-playlist-list"),
        {"library": str(library.id)},
    )

    assert response.status_code == 200
    results = response_results(response)
    assert len(results) == 1

    row = results[0]
    assert row["title"] == "My Playlist"
    assert row["channel_title"] == "Playlist Channel"
    assert row["video_count"] == 2
    assert row["runtime_seconds"] == pytest.approx(350)
    assert row["storage_bytes"] == 3500


def test_catalog_endpoints_do_not_expose_another_users_library():
    _owner, library = make_library("owner")
    channel = make_channel(
        library,
        "UC1111111111111111111111",
        "Private Channel",
    )
    make_video(
        library,
        channel,
        "private1234",
        "Private Video",
        upload_date=date(2026, 8, 1),
        size_bytes=100,
        duration_seconds=60,
    )

    other_user = get_user_model().objects.create_user(
        email="other@example.com",
        password="test-password",
    )
    client = authenticated_client(other_user)

    for route_name in (
        "catalog-channel-list",
        "catalog-playlist-list",
        "catalog-online-video-list",
    ):
        response = client.get(
            reverse(route_name),
            {"library": str(library.id)},
        )
        assert response.status_code == 200
        assert response_results(response) == []


def test_online_video_catalog_rejects_invalid_structured_filters():
    user, library = make_library("invalid-filters")
    client = authenticated_client(user)

    response = client.get(
        reverse("catalog-online-video-list"),
        {"library": "not-a-uuid"},
    )
    assert response.status_code == 400
    assert "library" in response.data

    response = client.get(
        reverse("catalog-online-video-list"),
        {
            "library": str(library.id),
            "uploaded_after": "not-a-date",
        },
    )
    assert response.status_code == 400
    assert "uploaded_after" in response.data

    response = client.get(
        reverse("catalog-online-video-list"),
        {
            "library": str(library.id),
            "kind": "not-a-video-kind",
        },
    )
    assert response.status_code == 400
    assert "kind" in response.data
