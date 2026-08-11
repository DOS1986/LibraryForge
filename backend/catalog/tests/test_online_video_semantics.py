import pytest
from django.contrib.auth import get_user_model

from catalog.models import (
    CanonicalFieldState,
    Channel,
    MediaVersion,
    OnlineVideo,
    Playlist,
    PlaylistMembership,
    SemanticMatch,
)
from catalog.services.online_video import (
    channel_semantic_key,
    online_video_semantic_key,
    playlist_semantic_key,
)
from catalog.services.resolver import resolve_library_semantics
from libraries.models import Library
from media.models import MediaFile, MediaItem
from metadata.models import MetadataSource


pytestmark = pytest.mark.django_db


def make_library(suffix: str, content_type="online_video"):
    owner = get_user_model().objects.create_user(
        email=f"online-{suffix}@example.com",
        password="test-password",
    )
    return Library.objects.create(
        owner=owner,
        name=f"Online {suffix}",
        path=f"/library/online-{suffix}",
        content_type=content_type,
    )


def make_file(library, relative_path="Channel/video.mkv"):
    item = MediaItem.objects.create(
        library=library,
        title="video",
    )
    file_name = relative_path.rsplit("/", 1)[-1]
    extension = file_name.rsplit(".", 1)[-1] if "." in file_name else ""
    media_file = MediaFile.objects.create(
        library=library,
        media_item=item,
        relative_path=relative_path,
        file_name=file_name,
        extension=extension,
        size_bytes=1000,
        duration_seconds=120,
        probe_status=MediaFile.ProbeStatus.OK,
        is_present=True,
    )
    return item, media_file


def add_source(
    media_file,
    source_type,
    raw_data=None,
    *,
    extracted_data=None,
    status=MetadataSource.Status.DETECTED,
):
    return MetadataSource.objects.create(
        media_item=media_file.media_item,
        media_file=media_file,
        source_type=source_type,
        status=status,
        extracted_data=extracted_data or {},
        raw_data=raw_data or {},
    )


def test_ytdlp_creates_channel_video_playlist_and_membership():
    library = make_library("ytdlp")
    item, media_file = make_file(library)

    add_source(
        media_file,
        MetadataSource.SourceType.YT_DLP,
        {
            "extractor_key": "Youtube",
            "id": "abc123def45",
            "title": "Building a Home Server",
            "description": "A complete home server build.",
            "channel": "Example Channel",
            "channel_id": "UC1234567890123456789012",
            "channel_url": "https://www.youtube.com/@example",
            "upload_date": "20260801",
            "webpage_url": "https://www.youtube.com/watch?v=abc123def45",
            "tags": ["homelab", "server"],
            "categories": ["Science & Technology"],
            "playlist_id": "PL12345678901234567890123456789012",
            "playlist_title": "Home Lab",
            "playlist_index": 4,
            "playlist_webpage_url": (
                "https://www.youtube.com/playlist?list="
                "PL12345678901234567890123456789012"
            ),
        },
    )

    result = resolve_library_semantics(library=library)

    assert result["matched"] == 1
    assert result["error_count"] == 0

    item.refresh_from_db()
    assert item.media_type == MediaItem.MediaType.ONLINE_VIDEO
    assert item.title == "Building a Home Server"
    assert item.description == "A complete home server build."
    assert str(item.release_date) == "2026-08-01"
    assert item.semantic_key == online_video_semantic_key(
        "youtube",
        "abc123def45",
    )

    channel = Channel.objects.get(library=library)
    assert channel.title == "Example Channel"
    assert channel.handle == "@example"
    assert channel.semantic_key == channel_semantic_key(
        "youtube",
        "UC1234567890123456789012",
    )

    video = OnlineVideo.objects.get(media_item=item)
    assert video.channel == channel
    assert video.provider == "youtube"
    assert video.source_id == "abc123def45"
    assert video.tags == ["homelab", "server"]

    playlist = Playlist.objects.get(library=library)
    assert playlist.title == "Home Lab"
    assert playlist.semantic_key == playlist_semantic_key(
        "youtube",
        "PL12345678901234567890123456789012",
    )

    membership = PlaylistMembership.objects.get(
        playlist=playlist,
        online_video=video,
    )
    assert membership.position == 4

    assert MediaVersion.objects.filter(
        media_item=item,
        media_file=media_file,
        is_primary=True,
    ).exists()

    match = SemanticMatch.objects.get(media_file=media_file)
    assert match.status == SemanticMatch.Status.MATCHED
    assert match.source == SemanticMatch.Source.YT_DLP
    assert match.confidence == 1.0

    # Rebuilding is idempotent.
    second = resolve_library_semantics(library=library)
    assert second["matched"] == 1
    assert Channel.objects.filter(library=library).count() == 1
    assert OnlineVideo.objects.filter(library=library).count() == 1
    assert Playlist.objects.filter(library=library).count() == 1
    assert PlaylistMembership.objects.count() == 1


def test_tubearchivist_is_preferred_and_preserves_embedded_version():
    library = make_library("ta")
    item, media_file = make_file(library)

    add_source(
        media_file,
        MetadataSource.SourceType.YT_DLP,
        {
            "extractor_key": "Youtube",
            "id": "abc123def45",
            "title": "yt-dlp title",
            "channel": "yt-dlp channel",
            "channel_id": "UC1234567890123456789012",
            "upload_date": "20260731",
            "webpage_url": "https://www.youtube.com/watch?v=abc123def45",
        },
    )

    add_source(
        media_file,
        MetadataSource.SourceType.TUBEARCHIVIST,
        {
            "ta": {
                "version": "ta-metadata-v1",
                "youtube_id": "abc123def45",
                "title": "TubeArchivist title",
                "description": "Indexed by TubeArchivist",
                "published": "2026-08-01",
                "vid_type": "shorts",
                "channel": {
                    "channel_id": "UC1234567890123456789012",
                    "channel_name": "TubeArchivist Channel",
                    "channel_url": "https://www.youtube.com/@taexample",
                },
                "playlists": [
                    {
                        "playlist_id": "PL12345678901234567890123456789012",
                        "playlist_name": "TA Playlist",
                        "playlist_position": 2,
                    }
                ],
            }
        },
    )

    result = resolve_library_semantics(library=library)
    assert result["matched"] == 1

    item.refresh_from_db()
    assert item.title == "TubeArchivist title"

    video = OnlineVideo.objects.get(media_item=item)
    assert video.video_kind == OnlineVideo.VideoKind.SHORT
    assert (
        video.canonical_metadata[
            "source_versions"
        ][
            "tubearchivist"
        ]
        == "ta-metadata-v1"
    )

    channel = Channel.objects.get(library=library)
    assert channel.title == "TubeArchivist Channel"

    playlist = Playlist.objects.get(library=library)
    assert playlist.title == "TA Playlist"

    match = SemanticMatch.objects.get(media_file=media_file)
    assert match.source == SemanticMatch.Source.TUBEARCHIVIST


def test_conflicting_source_ids_are_not_silently_reidentified():
    library = make_library("conflict")
    item, media_file = make_file(library)

    add_source(
        media_file,
        MetadataSource.SourceType.TUBEARCHIVIST,
        {
            "ta": {
                "youtube_id": "abc123def45",
                "title": "TA video",
            }
        },
    )
    add_source(
        media_file,
        MetadataSource.SourceType.YT_DLP,
        {
            "extractor_key": "Youtube",
            "id": "different01",
            "title": "Different yt-dlp video",
        },
    )

    result = resolve_library_semantics(library=library)

    assert result["conflict"] == 1
    assert result["matched"] == 0
    assert not OnlineVideo.objects.filter(media_item=item).exists()

    match = SemanticMatch.objects.get(media_file=media_file)
    assert match.status == SemanticMatch.Status.CONFLICT
    assert match.candidate_data["reason"] == "source_identity_disagreement"


def test_manual_title_lock_survives_online_metadata_refresh():
    library = make_library("manual-lock")
    item, media_file = make_file(library)

    item.title = "My Preferred Title"
    item.save(update_fields=["title", "updated_at"])

    CanonicalFieldState.objects.create(
        target_type=CanonicalFieldState.TargetType.MEDIA_ITEM,
        target_id=item.id,
        field_name="title",
        source=CanonicalFieldState.Source.MANUAL,
        value_snapshot="My Preferred Title",
        locked=True,
        updated_by=library.owner,
    )

    add_source(
        media_file,
        MetadataSource.SourceType.YT_DLP,
        {
            "extractor_key": "Youtube",
            "id": "abc123def45",
            "title": "Source Title",
            "channel": "Example",
            "channel_id": "UC1234567890123456789012",
        },
    )

    result = resolve_library_semantics(library=library)
    assert result["matched"] == 1

    item.refresh_from_db()
    assert item.title == "My Preferred Title"
    assert item.semantic_key == online_video_semantic_key(
        "youtube",
        "abc123def45",
    )


def test_online_resolver_does_not_run_for_generic_library():
    library = make_library("generic", content_type="generic")
    item, media_file = make_file(library)

    add_source(
        media_file,
        MetadataSource.SourceType.YT_DLP,
        {
            "extractor_key": "Youtube",
            "id": "abc123def45",
            "title": "Video",
        },
    )

    result = resolve_library_semantics(library=library)

    assert result["matched"] == 0
    assert result["unresolved"] == 0
    assert not OnlineVideo.objects.filter(media_item=item).exists()


def test_tubearchivist_path_identity_uses_embedded_display_metadata():
    library = make_library("ta-path")
    item, media_file = make_file(
        library,
        "UChYpy_1syqfkN-x1wLkecAw/UK4X75tY6_k.mp4",
    )

    add_source(
        media_file,
        MetadataSource.SourceType.EMBEDDED,
        {
            "format_tags": {
                "title": "Real Archived Video",
                "description": "Description embedded in the media file.",
                "artist": "Real TubeArchivist Channel",
                "date": "2026-07-15",
            },
            "stream_tags": [],
        },
        extracted_data={
            "title": "Real Archived Video",
            "description": "Description embedded in the media file.",
            "date": "2026-07-15",
        },
    )
    add_source(
        media_file,
        MetadataSource.SourceType.TUBEARCHIVIST,
        status=MetadataSource.Status.NOT_DETECTED,
    )
    add_source(
        media_file,
        MetadataSource.SourceType.YT_DLP,
        status=MetadataSource.Status.NOT_FOUND,
    )

    result = resolve_library_semantics(library=library)

    assert result["matched"] == 1
    assert result["unresolved"] == 0

    item.refresh_from_db()
    assert item.media_type == MediaItem.MediaType.ONLINE_VIDEO
    assert item.title == "Real Archived Video"
    assert item.description == "Description embedded in the media file."
    assert str(item.release_date) == "2026-07-15"
    assert item.semantic_key == online_video_semantic_key(
        "youtube",
        "UK4X75tY6_k",
    )

    channel = Channel.objects.get(library=library)
    assert channel.source_id == "UChYpy_1syqfkN-x1wLkecAw"
    assert channel.title == "Real TubeArchivist Channel"

    video = OnlineVideo.objects.get(media_item=item)
    assert video.source_id == "UK4X75tY6_k"
    assert video.channel == channel

    match = SemanticMatch.objects.get(media_file=media_file)
    assert match.status == SemanticMatch.Status.MATCHED
    assert match.source == SemanticMatch.Source.TUBEARCHIVIST_PATH
    assert match.confidence == pytest.approx(0.98)
    assert match.candidate_data["identity_basis"] == "tubearchivist_path"
    assert match.candidate_data["identity_source_ref"].startswith(
        "tubearchivist-path:"
    )

    title_state = CanonicalFieldState.objects.get(
        target_type=CanonicalFieldState.TargetType.MEDIA_ITEM,
        target_id=item.id,
        field_name="title",
    )
    assert title_state.source == CanonicalFieldState.Source.EMBEDDED


def test_invalid_online_video_path_remains_unresolved_without_stable_id():
    library = make_library("invalid-path")
    _item, media_file = make_file(
        library,
        "Some Channel/not-a-youtube-id.mp4",
    )

    add_source(
        media_file,
        MetadataSource.SourceType.EMBEDDED,
        {
            "format_tags": {
                "title": "Descriptive metadata is not identity",
                "artist": "Example Channel",
            },
        },
        extracted_data={
            "title": "Descriptive metadata is not identity",
        },
    )

    result = resolve_library_semantics(library=library)

    assert result["matched"] == 0
    assert result["unresolved"] == 1
    match = SemanticMatch.objects.get(media_file=media_file)
    assert match.status == SemanticMatch.Status.UNRESOLVED
    assert match.candidate_data["reason"] == "stable_source_identity_missing"


def test_path_identity_conflicts_with_different_explicit_ytdlp_id():
    library = make_library("path-conflict")
    item, media_file = make_file(
        library,
        "UChYpy_1syqfkN-x1wLkecAw/UK4X75tY6_k.mp4",
    )

    add_source(
        media_file,
        MetadataSource.SourceType.YT_DLP,
        {
            "extractor_key": "Youtube",
            "id": "abc123def45",
            "title": "Different identity",
            "channel_id": "UChYpy_1syqfkN-x1wLkecAw",
        },
    )

    result = resolve_library_semantics(library=library)

    assert result["conflict"] == 1
    assert result["matched"] == 0
    assert not OnlineVideo.objects.filter(media_item=item).exists()

    match = SemanticMatch.objects.get(media_file=media_file)
    assert match.status == SemanticMatch.Status.CONFLICT
    assert match.candidate_data["reason"] == "source_identity_disagreement"
    assert "tubearchivist_path" in match.candidate_data["sources"]
