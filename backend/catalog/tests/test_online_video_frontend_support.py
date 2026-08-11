from datetime import date

import pytest
from django.urls import reverse

from catalog.models import PlaylistMembership
from catalog.tests.test_online_video_catalog_api import (
    authenticated_client,
    make_channel,
    make_library,
    make_playlist,
    make_video,
    response_results,
)


pytestmark = pytest.mark.django_db


def test_playlist_filtered_videos_can_be_ordered_by_membership_position():
    user, library = make_library("playlist-order")
    channel = make_channel(
        library,
        "UC2222222222222222222222",
        "Ordered Channel",
    )
    alphabetically_first = make_video(
        library,
        channel,
        "aaaaa111111",
        "Alpha Video",
        upload_date=date(2026, 8, 1),
        size_bytes=100,
        duration_seconds=10,
    )
    alphabetically_second = make_video(
        library,
        channel,
        "zzzzz222222",
        "Zulu Video",
        upload_date=date(2026, 8, 2),
        size_bytes=100,
        duration_seconds=10,
    )
    playlist = make_playlist(
        library,
        channel,
        "PL22222222222222222222222222222222",
        "Ordered Playlist",
    )

    PlaylistMembership.objects.create(
        playlist=playlist,
        online_video=alphabetically_second,
        position=1,
    )
    PlaylistMembership.objects.create(
        playlist=playlist,
        online_video=alphabetically_first,
        position=2,
    )

    client = authenticated_client(user)
    response = client.get(
        reverse("catalog-online-video-list"),
        {
            "library": str(library.id),
            "playlist": str(playlist.id),
            "ordering": "playlist_memberships__position",
        },
    )

    assert response.status_code == 200
    results = response_results(response)
    assert [row["title"] for row in results] == [
        "Zulu Video",
        "Alpha Video",
    ]
