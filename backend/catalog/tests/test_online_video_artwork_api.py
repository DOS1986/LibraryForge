from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.urls import reverse

from catalog.models import ArtworkFile, PlaylistMembership
from catalog.tests.test_online_video_catalog_api import (
    authenticated_client,
    make_channel,
    make_library,
    make_playlist,
    make_video,
    response_results,
)


pytestmark = pytest.mark.django_db


def _selected_artwork(library, target_type, target_id, relative_path):
    return ArtworkFile.objects.create(
        library=library,
        target_type=target_type,
        target_id=target_id,
        artwork_type=ArtworkFile.ArtworkType.PRIMARY,
        source_name="video-thumb",
        relative_path=relative_path,
        file_name="art.jpg",
        extension="jpg",
        is_present=True,
        is_selected=True,
    )


def test_catalog_apis_expose_selected_artwork_urls():
    user, library = make_library("art-api")
    channel = make_channel(
        library,
        "UC5555555555555555555555",
        "Artwork API Channel",
    )
    video = make_video(
        library,
        channel,
        "artapi12345",
        "Artwork API Video",
        upload_date=date(2026, 8, 1),
        size_bytes=100,
        duration_seconds=60,
    )
    playlist = make_playlist(
        library,
        channel,
        "PL55555555555555555555555555555555",
        "Artwork API Playlist",
    )
    PlaylistMembership.objects.create(
        playlist=playlist,
        online_video=video,
        position=1,
    )

    channel_art = _selected_artwork(
        library,
        ArtworkFile.TargetType.CHANNEL,
        channel.id,
        "channel-poster.jpg",
    )
    video_art = _selected_artwork(
        library,
        ArtworkFile.TargetType.MEDIA_ITEM,
        video.media_item_id,
        "video-poster.jpg",
    )
    playlist_art = _selected_artwork(
        library,
        ArtworkFile.TargetType.PLAYLIST,
        playlist.id,
        "playlist-poster.jpg",
    )

    client = authenticated_client(user)

    channel_response = client.get(
        reverse("catalog-channel-list"),
        {"library": str(library.id)},
    )
    assert channel_response.status_code == 200
    assert response_results(channel_response)[0]["artwork_url"] == (
        f"/api/artwork-files/{channel_art.id}/content/"
    )

    video_response = client.get(
        reverse("catalog-online-video-list"),
        {"library": str(library.id)},
    )
    assert video_response.status_code == 200
    assert response_results(video_response)[0]["artwork_url"] == (
        f"/api/artwork-files/{video_art.id}/content/"
    )

    playlist_response = client.get(
        reverse("catalog-playlist-list"),
        {"library": str(library.id)},
    )
    assert playlist_response.status_code == 200
    assert response_results(playlist_response)[0]["artwork_url"] == (
        f"/api/artwork-files/{playlist_art.id}/content/"
    )


def test_embedded_artwork_content_is_extracted_with_ffmpeg(tmp_path):
    user, library = make_library("embedded-api")
    library.path = str(tmp_path)
    library.save(update_fields=["path", "updated_at"])

    channel = make_channel(
        library,
        "UC6666666666666666666666",
        "Embedded API Channel",
    )
    video = make_video(
        library,
        channel,
        "embedapi123",
        "Embedded API Video",
        upload_date=date(2026, 8, 1),
        size_bytes=100,
        duration_seconds=60,
    )

    media_file = video.media_item.files.get()
    media_path = tmp_path / media_file.relative_path
    media_path.parent.mkdir(parents=True)
    media_path.write_bytes(b"not-real-video")
    media_file.raw_probe = {
        "streams": [
            {
                "index": 3,
                "disposition": {"attached_pic": 1},
            }
        ]
    }
    media_file.save(update_fields=["raw_probe", "updated_at"])

    artwork = ArtworkFile.objects.create(
        library=library,
        target_type=ArtworkFile.TargetType.MEDIA_ITEM,
        target_id=video.media_item_id,
        artwork_type=ArtworkFile.ArtworkType.PRIMARY,
        source_name="embedded-cover",
        relative_path=f"@embedded/{media_file.id}/3.png",
        file_name="embedded.png",
        extension="png",
        is_present=True,
        is_selected=True,
    )

    client = authenticated_client(user)

    with patch(
        "catalog.artwork_views.subprocess.run",
        return_value=SimpleNamespace(
            returncode=0,
            stdout=b"png-image-bytes",
            stderr=b"",
        ),
    ) as run:
        response = client.get(
            f"/api/artwork-files/{artwork.id}/content/"
        )

    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    assert response.content == b"png-image-bytes"

    command = run.call_args.args[0]
    assert "-map" in command
    assert "0:3" in command
    assert "shell" not in run.call_args.kwargs
