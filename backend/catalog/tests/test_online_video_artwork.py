from datetime import date
from pathlib import Path

import pytest

from catalog.models import ArtworkFile, PlaylistMembership
from catalog.services.artwork import scan_library_artwork
from catalog.tests.test_online_video_catalog_api import (
    make_channel,
    make_library,
    make_playlist,
    make_video,
)


pytestmark = pytest.mark.django_db


def _real_library(tmp_path: Path, suffix: str):
    user, library = make_library(suffix)
    library.path = str(tmp_path)
    library.save(update_fields=["path", "updated_at"])
    return user, library


def test_online_video_adjacent_thumbnail_targets_media_item(tmp_path):
    _user, library = _real_library(tmp_path, "art-video")
    channel = make_channel(
        library,
        "UChYpy_1syqfkN-x1wLkecAw",
        "Example Channel",
    )
    video = make_video(
        library,
        channel,
        "UK4X75tY6_k",
        "Example Video",
        upload_date=date(2026, 8, 1),
        size_bytes=100,
        duration_seconds=60,
    )

    channel_dir = tmp_path / channel.source_id
    channel_dir.mkdir()
    (channel_dir / f"{video.source_id}.jpg").write_bytes(b"thumbnail")

    result = scan_library_artwork(library=library)

    assert result["error_count"] == 0
    artwork = ArtworkFile.objects.get(
        library=library,
        target_type=ArtworkFile.TargetType.MEDIA_ITEM,
        target_id=video.media_item_id,
        artwork_type=ArtworkFile.ArtworkType.PRIMARY,
    )
    assert artwork.source_name == "video-thumb"
    assert artwork.is_selected is True


def test_online_video_channel_folder_artwork_targets_channel(tmp_path):
    _user, library = _real_library(tmp_path, "art-channel")
    channel = make_channel(
        library,
        "UC1234567890123456789012",
        "Channel Artwork",
    )
    make_video(
        library,
        channel,
        "abc123def45",
        "Channel Video",
        upload_date=date(2026, 8, 1),
        size_bytes=100,
        duration_seconds=60,
    )

    channel_dir = tmp_path / channel.source_id
    channel_dir.mkdir()
    (channel_dir / "poster.jpg").write_bytes(b"channel-poster")

    scan_library_artwork(library=library)

    artwork = ArtworkFile.objects.get(
        library=library,
        target_type=ArtworkFile.TargetType.CHANNEL,
        target_id=channel.id,
    )
    assert artwork.artwork_type == ArtworkFile.ArtworkType.PRIMARY
    assert artwork.is_selected is True


def test_playlist_id_artwork_targets_playlist(tmp_path):
    _user, library = _real_library(tmp_path, "art-playlist")
    channel = make_channel(
        library,
        "UC2222222222222222222222",
        "Playlist Channel",
    )
    video = make_video(
        library,
        channel,
        "playlist1234",
        "Playlist Video",
        upload_date=date(2026, 8, 1),
        size_bytes=100,
        duration_seconds=60,
    )
    playlist = make_playlist(
        library,
        channel,
        "PL22222222222222222222222222222222",
        "Playlist Artwork",
    )
    PlaylistMembership.objects.create(
        playlist=playlist,
        online_video=video,
        position=1,
    )

    (tmp_path / f"{playlist.source_id}.jpg").write_bytes(b"playlist")

    scan_library_artwork(library=library)

    artwork = ArtworkFile.objects.get(
        library=library,
        target_type=ArtworkFile.TargetType.PLAYLIST,
        target_id=playlist.id,
    )
    assert artwork.source_name == "playlist-art"


def test_embedded_cover_is_indexed_without_writing_sidecar(tmp_path):
    _user, library = _real_library(tmp_path, "art-embedded")
    channel = make_channel(
        library,
        "UC3333333333333333333333",
        "Embedded Channel",
    )
    video = make_video(
        library,
        channel,
        "embed123456",
        "Embedded Video",
        upload_date=date(2026, 8, 1),
        size_bytes=100,
        duration_seconds=60,
    )

    media_file = video.media_item.files.get()
    media_file.raw_probe = {
        "streams": [
            {
                "index": 3,
                "codec_name": "mjpeg",
                "codec_type": "video",
                "disposition": {"attached_pic": 1},
                "tags": {"title": "Cover"},
            }
        ]
    }
    media_file.modified_ns = 123
    media_file.save(update_fields=["raw_probe", "modified_ns", "updated_at"])

    scan_library_artwork(library=library)

    artwork = ArtworkFile.objects.get(
        library=library,
        target_type=ArtworkFile.TargetType.MEDIA_ITEM,
        target_id=video.media_item_id,
    )
    assert artwork.relative_path == f"@embedded/{media_file.id}/3.png"
    assert artwork.source_name == "embedded-cover"
    assert artwork.size_bytes == 0
    assert not (tmp_path / artwork.file_name).exists()


def test_labeled_embedded_channel_art_targets_channel(tmp_path):
    _user, library = _real_library(tmp_path, "art-embedded-channel")
    channel = make_channel(
        library,
        "UC4444444444444444444444",
        "Embedded Channel Art",
    )
    video = make_video(
        library,
        channel,
        "embed654321",
        "Embedded Channel Video",
        upload_date=date(2026, 8, 1),
        size_bytes=100,
        duration_seconds=60,
    )

    media_file = video.media_item.files.get()
    media_file.raw_probe = {
        "streams": [
            {
                "index": 4,
                "codec_name": "png",
                "codec_type": "video",
                "disposition": {"attached_pic": 1},
                "tags": {"title": "Channel Art"},
            }
        ]
    }
    media_file.save(update_fields=["raw_probe", "updated_at"])

    scan_library_artwork(library=library)

    artwork = ArtworkFile.objects.get(
        library=library,
        target_type=ArtworkFile.TargetType.CHANNEL,
        target_id=channel.id,
    )
    assert artwork.source_name == "embedded-channel"
