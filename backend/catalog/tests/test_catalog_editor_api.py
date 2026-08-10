import pytest

from django.contrib.auth import (
    get_user_model,
)
from django.urls import reverse

from rest_framework.test import APIClient

from catalog.models import (
    CanonicalFieldState,
)
from catalog.services.parser import (
    movie_semantic_key,
)
from libraries.models import Library
from media.models import MediaItem


pytestmark = pytest.mark.django_db


def create_movie():
    user = (
        get_user_model()
        .objects
        .create_user(
            email="catalog-editor@example.com",
            password="test-password",
        )
    )

    library = Library.objects.create(
        owner=user,
        name="Movies",
        path="/library/movies",
        content_type="movies",
    )

    movie = MediaItem.objects.create(
        library=library,
        media_type=(
            MediaItem
            .MediaType
            .MOVIE
        ),
        semantic_key=(
            movie_semantic_key(
                "2067",
                2020,
            )
        ),
        title="2067",
        canonical_metadata={
            "semantic": {
                "kind": "movie",
                "year": 2020,
            }
        },
    )

    return (
        user,
        movie,
    )


def test_movie_editor_get_and_patch():
    user, movie = create_movie()

    client = APIClient()
    client.force_authenticate(
        user=user
    )

    url = reverse(
        "catalog-editor-movie",
        kwargs={
            "item_id": movie.id,
        },
    )

    response = client.get(
        url
    )

    assert response.status_code == 200
    assert response.data["kind"] == "movie"
    assert (
        response.data[
            "metadata"
        ][
            "title"
        ]
        == "2067"
    )

    response = client.patch(
        url,
        {
            "title": "2067 — Canonical",
            "tagline": "The future awaits.",
            "genres": [
                "Science Fiction",
            ],
            "external_ids": {
                "imdb": "tt1918734",
            },
            "note": "Catalog editor test.",
        },
        format="json",
    )

    assert response.status_code == 200

    movie.refresh_from_db()

    assert (
        movie.title
        == "2067 — Canonical"
    )

    assert (
        movie.tagline
        == "The future awaits."
    )

    assert movie.genres == [
        "Science Fiction",
    ]

    assert (
        CanonicalFieldState.objects
        .filter(
            target_type="media_item",
            target_id=movie.id,
            field_name="title",
            source="manual",
            locked=True,
        )
        .exists()
    )
