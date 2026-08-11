import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from catalog.models import Channel, OnlineVideo
from libraries.models import Library
from media.models import MediaFile, MediaItem


pytestmark = pytest.mark.django_db


def make_online_video_file():
    user = get_user_model().objects.create_user(
        email="files-channel@example.com",
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
        source_id="UChYpy_1syqfkN-x1wLkecAw",
        semantic_key="channel:youtube:UChYpy_1syqfkN-x1wLkecAw",
        title="Example Channel",
        sort_title="Example Channel",
    )
    item = MediaItem.objects.create(
        library=library,
        title="Example Video",
        media_type=MediaItem.MediaType.ONLINE_VIDEO,
        semantic_key="online-video:youtube:UK4X75tY6_k",
    )
    OnlineVideo.objects.create(
        library=library,
        media_item=item,
        channel=channel,
        provider="youtube",
        source_id="UK4X75tY6_k",
    )
    media_file = MediaFile.objects.create(
        library=library,
        media_item=item,
        relative_path=(
            "UChYpy_1syqfkN-x1wLkecAw/"
            "UK4X75tY6_k.mp4"
        ),
        file_name="UK4X75tY6_k.mp4",
        extension="mp4",
        size_bytes=1234,
        probe_status=MediaFile.ProbeStatus.OK,
        is_present=True,
    )
    return user, library, channel, media_file


def authenticated_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def response_results(response):
    if isinstance(response.data, dict) and "results" in response.data:
        return response.data["results"]
    return response.data


def test_media_file_api_exposes_online_video_channel():
    user, library, channel, media_file = make_online_video_file()
    client = authenticated_client(user)

    response = client.get(
        reverse("media-file-list"),
        {"library": str(library.id)},
    )

    assert response.status_code == 200
    results = response_results(response)
    assert len(results) == 1
    assert results[0]["id"] == str(media_file.id)
    assert results[0]["channel_id"] == str(channel.id)
    assert results[0]["channel_title"] == "Example Channel"


def test_library_asset_api_exposes_and_searches_channel():
    user, library, channel, media_file = make_online_video_file()
    client = authenticated_client(user)

    response = client.get(
        reverse("library-asset-list"),
        {
            "library": str(library.id),
            "search": "Example Channel",
        },
    )

    assert response.status_code == 200
    results = response_results(response)
    assert len(results) == 1
    assert results[0]["id"] == str(media_file.id)
    assert results[0]["channel_id"] == str(channel.id)
    assert results[0]["channel_title"] == "Example Channel"


def test_library_browser_displays_channel_name_for_tubearchivist_root_folder():
    user, library, channel, _media_file = make_online_video_file()
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
    assert len(results) == 1
    assert results[0]["entry_type"] == "folder"
    assert results[0]["name"] == channel.source_id
    assert results[0]["title"] == "Example Channel"
