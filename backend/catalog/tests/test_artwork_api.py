import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from catalog.models import ArtworkFile
from libraries.models import Library


pytestmark = pytest.mark.django_db


def test_select_artwork_requires_owned_library(tmp_path):
    owner = get_user_model().objects.create_user(
        email="owner@example.com",
        password="test-password",
    )

    other = get_user_model().objects.create_user(
        email="other@example.com",
        password="test-password",
    )

    library = Library.objects.create(
        owner=owner,
        name="Movies",
        path=str(tmp_path),
        content_type="movies",
    )

    artwork = ArtworkFile.objects.create(
        library=library,
        target_type="media_item",
        target_id="00000000-0000-0000-0000-000000000001",
        artwork_type="primary",
        source_name="poster",
        relative_path="Movie/poster.jpg",
        file_name="poster.jpg",
        extension="jpg",
        is_present=True,
    )

    client = APIClient()
    client.force_authenticate(other)

    response = client.post(
        f"/api/artwork-files/{artwork.id}/select/",
        {},
        format="json",
    )

    assert response.status_code == 404


def test_artwork_content_is_authenticated_and_served(tmp_path):
    owner = get_user_model().objects.create_user(
        email="owner2@example.com",
        password="test-password",
    )

    library = Library.objects.create(
        owner=owner,
        name="Movies",
        path=str(tmp_path),
        content_type="movies",
    )

    movie_dir = tmp_path / "Movie"
    movie_dir.mkdir()
    image = movie_dir / "poster.jpg"
    image.write_bytes(b"not-a-real-jpeg-but-served")

    artwork = ArtworkFile.objects.create(
        library=library,
        target_type="media_item",
        target_id="00000000-0000-0000-0000-000000000001",
        artwork_type="primary",
        source_name="poster",
        relative_path="Movie/poster.jpg",
        file_name="poster.jpg",
        extension="jpg",
        is_present=True,
    )

    client = APIClient()

    anonymous = client.get(
        f"/api/artwork-files/{artwork.id}/content/"
    )

    assert anonymous.status_code in {401, 403}

    client.force_authenticate(owner)

    response = client.get(
        f"/api/artwork-files/{artwork.id}/content/"
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "image/jpeg"
