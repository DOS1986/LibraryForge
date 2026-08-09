import pytest

from django.contrib.auth import (
    get_user_model,
)

from catalog.models import Series

from catalog.services.parser import (
    SemanticCandidate,
    series_semantic_key,
)

from catalog.services.resolver import (
    _series_object,
)

from libraries.models import Library


pytestmark = pytest.mark.django_db


def create_tv_library(
    name: str,
):
    user = (
        get_user_model()
        .objects
        .create_user(
            email=(
                f"{name.lower().replace(' ', '-')}@example.com"
            ),
            password="test-password",
        )
    )

    return Library.objects.create(
        owner=user,
        name=name,
        path=(
            f"/library/{name}"
        ),
        content_type="tv",
    )


def test_known_nfo_year_upgrades_existing_yearless_series():
    library = create_tv_library(
        "TV"
    )

    existing = (
        Series.objects.create(
            library=library,
            title="The Expanse",
            sort_title="The Expanse",
            semantic_key=(
                series_semantic_key(
                    "The Expanse",
                    None,
                )
            ),
        )
    )

    (
        resolved,
        key,
    ) = _series_object(
        library=library,
        candidate=(
            SemanticCandidate(
                kind="episode",
                series_title=(
                    "The Expanse"
                ),
                series_year=2015,
                season_number=1,
                episode_number=1,
            )
        ),
    )

    resolved.refresh_from_db()

    assert (
        resolved.id
        == existing.id
    )

    assert (
        resolved.start_year
        == 2015
    )

    assert key == (
        series_semantic_key(
            "The Expanse",
            2015,
        )
    )


def test_yearless_filename_reuses_only_matching_yearful_series():
    library = create_tv_library(
        "TV Yearful"
    )

    existing = (
        Series.objects.create(
            library=library,
            title="The Expanse",
            sort_title="The Expanse",
            semantic_key=(
                series_semantic_key(
                    "The Expanse",
                    2015,
                )
            ),
            start_year=2015,
        )
    )

    (
        resolved,
        _key,
    ) = _series_object(
        library=library,
        candidate=(
            SemanticCandidate(
                kind="episode",
                series_title=(
                    "The Expanse"
                ),
                series_year=None,
                season_number=1,
                episode_number=2,
            )
        ),
    )

    assert (
        resolved.id
        == existing.id
    )


def test_plus_and_slash_series_names_reuse_same_series():
    library = create_tv_library(
        "TV Punctuation"
    )

    existing = (
        Series.objects.create(
            library=library,
            title="Alpha+Beta",
            sort_title="Alpha+Beta",
            semantic_key=(
                series_semantic_key(
                    "Alpha+Beta",
                    None,
                )
            ),
        )
    )

    (
        resolved,
        _key,
    ) = _series_object(
        library=library,
        candidate=(
            SemanticCandidate(
                kind="episode",
                series_title=(
                    "Alpha/Beta"
                ),
                season_number=2,
                episode_number=5,
            )
        ),
    )

    assert (
        resolved.id
        == existing.id
    )
