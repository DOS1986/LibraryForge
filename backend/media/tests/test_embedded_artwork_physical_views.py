import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.models import ArtworkFile, Channel, OnlineVideo
from libraries.models import Library
from media.models import MediaFile, MediaItem


pytestmark = pytest.mark.django_db


CHANNEL_ID = "UChYpy_1syqfkN-x1wLkecAw"
VIDEO_ID = "UK4X75tY6_k"


def make_library_with_artwork():
    user = get_user_model().objects.create_user(
        email="embedded-artwork-files@example.com",
        password="test-password",
    )
    library = Library.objects.create(
        owner=user,
        name="TubeArchivist",
        path="/youtube",
        content_type="online_video",
    )
    channel = Channel.objects.create(
        library=library,
        provider="youtube",
        source_id=CHANNEL_ID,
        semantic_key=f"channel:youtube:{CHANNEL_ID}",
        title="Example Channel",
        sort_title="Example Channel",
    )
    item = MediaItem.objects.create(
        library=library,
        title="Example Video",
        media_type=MediaItem.MediaType.ONLINE_VIDEO,
        semantic_key=f"online-video:youtube:{VIDEO_ID}",
    )
    OnlineVideo.objects.create(
        library=library,
        media_item=item,
        channel=channel,
        provider="youtube",
        source_id=VIDEO_ID,
    )
    media_file = MediaFile.objects.create(
        library=library,
        media_item=item,
        relative_path=f"{CHANNEL_ID}/{VIDEO_ID}.mp4",
        file_name=f"{VIDEO_ID}.mp4",
        extension="mp4",
        size_bytes=1234,
        probe_status=MediaFile.ProbeStatus.OK,
        is_present=True,
    )
    sidecar = ArtworkFile.objects.create(
        library=library,
        target_type=ArtworkFile.TargetType.MEDIA_ITEM,
        target_id=item.id,
        artwork_type=ArtworkFile.ArtworkType.PRIMARY,
        source_name="video-sidecar",
        relative_path=f"{CHANNEL_ID}/{VIDEO_ID}.jpg",
        file_name=f"{VIDEO_ID}.jpg",
        extension="jpg",
        size_bytes=50,
        modified_ns=1,
        is_selected=True,
        is_present=True,
    )
    embedded = ArtworkFile.objects.create(
        library=library,
        target_type=ArtworkFile.TargetType.MEDIA_ITEM,
        target_id=item.id,
        artwork_type=ArtworkFile.ArtworkType.PRIMARY,
        source_name="embedded-cover",
        relative_path=f"@embedded/{media_file.id}/3.png",
        file_name="embedded-stream-3.png",
        extension="png",
        size_bytes=9999,
        modified_ns=0,
        is_selected=False,
        is_present=True,
    )
    return user, library, media_file, sidecar, embedded


def authenticated_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def response_results(response):
    if isinstance(response.data, dict) and "results" in response.data:
        return response.data["results"]
    return response.data


def test_library_assets_exclude_virtual_embedded_artwork():
    user, library, media_file, sidecar, embedded = make_library_with_artwork()
    client = authenticated_client(user)

    response = client.get(
        reverse("library-asset-list"),
        {"library": str(library.id)},
    )

    assert response.status_code == 200
    results = response_results(response)
    ids = {row["id"] for row in results}

    assert str(media_file.id) in ids
    assert str(sidecar.id) in ids
    assert str(embedded.id) not in ids
    assert all(
        not row["relative_path"].startswith("@embedded/")
        for row in results
    )


def test_library_browser_ignores_virtual_artwork_in_physical_totals():
    user, library, _media_file, _sidecar, _embedded = make_library_with_artwork()
    client = authenticated_client(user)

    response = client.get(
        reverse("library-browser-list"),
        {
            "library": str(library.id),
            "content": "files",
            "path": "",
        },
    )

    assert response.status_code == 200
    results = response_results(response)

    assert all(row["name"] != "@embedded" for row in results)

    channel_folder = next(
        row for row in results
        if row["entry_type"] == "folder" and row["name"] == CHANNEL_ID
    )

    # One physical media file + one physical sidecar image. The virtual
    # embedded-artwork record must not add a third file or its synthetic size.
    assert channel_folder["file_count"] == 2
    assert channel_folder["artwork_count"] == 1
    assert channel_folder["size_bytes"] == 1284
