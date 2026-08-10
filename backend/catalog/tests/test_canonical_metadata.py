import pytest

from django.contrib.auth import (
    get_user_model,
)

from catalog.models import (
    CanonicalFieldState,
    Episode,
    MetadataChangeSet,
    Season,
    Series,
)
from catalog.services.canonical import (
    make_primary_version,
    update_episode_metadata,
    update_media_version,
    update_movie_metadata,
    update_series_metadata,
)
from catalog.services.parser import (
    SemanticCandidate,
    episode_semantic_key,
    movie_semantic_key,
    series_semantic_key,
)
from catalog.services.resolver import (
    _ensure_version,
    _episode_item,
    _movie_item,
    _series_object,
)
from libraries.models import Library
from media.models import (
    MediaFile,
    MediaItem,
)


pytestmark = pytest.mark.django_db


def make_user(
    suffix: str,
):
    return (
        get_user_model()
        .objects
        .create_user(
            email=(
                f"canonical-{suffix}@example.com"
            ),
            password="test-password",
        )
    )


def make_library(
    *,
    suffix: str,
    content_type: str,
):
    return Library.objects.create(
        owner=make_user(
            suffix
        ),
        name=(
            f"Canonical {suffix}"
        ),
        path=(
            f"/library/canonical-{suffix}"
        ),
        content_type=content_type,
    )


def make_media_file(
    *,
    library,
    media_item,
    relative_path: str,
):
    return MediaFile.objects.create(
        library=library,
        media_item=media_item,
        relative_path=relative_path,
        file_name=(
            relative_path
            .rsplit(
                "/",
                1,
            )[-1]
        ),
        extension="mkv",
        size_bytes=1000,
        duration_seconds=120.0,
        video_codec="hevc",
        width=3840,
        height=2160,
        audio_codec="truehd",
        audio_channels=8,
        probe_status=(
            MediaFile
            .ProbeStatus
            .OK
        ),
    )


def test_movie_manual_metadata_creates_field_state_and_history():
    library = make_library(
        suffix="movie-history",
        content_type="movies",
    )

    item = MediaItem.objects.create(
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

    update_movie_metadata(
        media_item=item,
        values={
            "title": "2067: The Future",
            "year": 2021,
            "genres": [
                "Science Fiction",
            ],
        },
        user=library.owner,
        note="Manual catalog cleanup.",
    )

    item.refresh_from_db()

    assert (
        item.title
        == "2067: The Future"
    )

    assert (
        item.canonical_metadata[
            "semantic"
        ][
            "year"
        ]
        == 2021
    )

    assert item.genres == [
        "Science Fiction",
    ]

    title_state = (
        CanonicalFieldState.objects
        .get(
            target_type="media_item",
            target_id=item.id,
            field_name="title",
        )
    )

    assert title_state.source == "manual"
    assert title_state.locked is True

    change = (
        MetadataChangeSet.objects
        .get(
            target_type="media_item",
            target_id=item.id,
        )
    )

    assert (
        change.changes[
            "title"
        ][
            "old"
        ]
        == "2067"
    )

    # Canonical display editing does not rewrite semantic identity.
    assert (
        item.semantic_key
        == movie_semantic_key(
            "2067",
            2020,
        )
    )


def test_movie_resolver_preserves_manual_title_and_year():
    library = make_library(
        suffix="movie-lock",
        content_type="movies",
    )

    item = MediaItem.objects.create(
        library=library,
        media_type=(
            MediaItem
            .MediaType
            .MOVIE
        ),
        semantic_key=(
            movie_semantic_key(
                "Blade Runner",
                1982,
            )
        ),
        title="Blade Runner",
        canonical_metadata={
            "semantic": {
                "kind": "movie",
                "year": 1982,
            }
        },
    )

    media_file = make_media_file(
        library=library,
        media_item=item,
        relative_path=(
            "Blade Runner (1982)/"
            "Blade Runner.mkv"
        ),
    )

    update_movie_metadata(
        media_item=item,
        values={
            "title": "Blade Runner — Final Cut",
            "year": 1982,
        },
        user=library.owner,
    )

    _movie_item(
        library=library,
        media_file=media_file,
        candidate=SemanticCandidate(
            kind="movie",
            title="Blade Runner",
            year=1982,
            source="folder",
            confidence=0.95,
        ),
    )

    item.refresh_from_db()

    assert (
        item.title
        == "Blade Runner — Final Cut"
    )


def test_series_resolver_preserves_manual_display_title():
    library = make_library(
        suffix="series-lock",
        content_type="tv",
    )

    series = Series.objects.create(
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

    update_series_metadata(
        series=series,
        values={
            "title": "The Expanse (TV)",
            "sort_title": "Expanse, The",
        },
        user=library.owner,
    )

    resolved, _key = _series_object(
        library=library,
        candidate=SemanticCandidate(
            kind="episode",
            series_title="The Expanse",
            series_year=2015,
            season_number=1,
            episode_number=1,
            source="folder",
            confidence=0.95,
        ),
    )

    resolved.refresh_from_db()

    assert (
        resolved.title
        == "The Expanse (TV)"
    )

    assert (
        resolved.sort_title
        == "Expanse, The"
    )


def test_episode_resolver_preserves_manual_episode_title():
    library = make_library(
        suffix="episode-lock",
        content_type="tv",
    )

    series = Series.objects.create(
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

    season = Season.objects.create(
        series=series,
        season_number=1,
        title="Season 1",
    )

    item = MediaItem.objects.create(
        library=library,
        media_type=(
            MediaItem
            .MediaType
            .TV_EPISODE
        ),
        semantic_key=(
            episode_semantic_key(
                series.semantic_key,
                1,
                3,
            )
        ),
        title="Episode 3",
    )

    episode = Episode.objects.create(
        media_item=item,
        season=season,
        episode_number=3,
    )

    media_file = make_media_file(
        library=library,
        media_item=item,
        relative_path=(
            "The Expanse/Season 01/"
            "The Expanse S01E03.mkv"
        ),
    )

    update_episode_metadata(
        episode=episode,
        values={
            "title": "Remember the Cant — Custom",
        },
        user=library.owner,
    )

    _episode_item(
        library=library,
        media_file=media_file,
        candidate=SemanticCandidate(
            kind="episode",
            title="Remember the Cant",
            episode_title="Remember the Cant",
            series_title="The Expanse",
            series_year=2015,
            season_number=1,
            episode_number=3,
            source="folder",
            confidence=0.95,
        ),
    )

    item.refresh_from_db()

    assert (
        item.title
        == "Remember the Cant — Custom"
    )


def test_version_editor_survives_semantic_refresh_and_primary_change():
    library = make_library(
        suffix="version-lock",
        content_type="movies",
    )

    item = MediaItem.objects.create(
        library=library,
        media_type=(
            MediaItem
            .MediaType
            .MOVIE
        ),
        semantic_key=(
            movie_semantic_key(
                "Alien",
                1979,
            )
        ),
        title="Alien",
    )

    first_file = make_media_file(
        library=library,
        media_item=item,
        relative_path=(
            "Alien (1979)/Alien 1080p.mkv"
        ),
    )

    second_file = make_media_file(
        library=library,
        media_item=item,
        relative_path=(
            "Alien (1979)/Alien 2160p.mkv"
        ),
    )

    first = _ensure_version(
        media_file=first_file,
        media_item=item,
    )

    second = _ensure_version(
        media_file=second_file,
        media_item=item,
    )

    update_media_version(
        version=second,
        values={
            "name": "4K Remux",
            "edition": "Theatrical",
        },
        user=library.owner,
    )

    make_primary_version(
        version=second,
        user=library.owner,
    )

    _ensure_version(
        media_file=second_file,
        media_item=item,
        edition="",
    )

    first.refresh_from_db()
    second.refresh_from_db()

    assert second.name == "4K Remux"
    assert second.edition == "Theatrical"
    assert second.is_primary is True
    assert first.is_primary is False


def test_resolver_records_automatic_field_provenance():
    library = make_library(
        suffix="automatic-provenance",
        content_type="movies",
    )

    placeholder = MediaItem.objects.create(
        library=library,
        title="2067 (2020)",
    )

    media_file = make_media_file(
        library=library,
        media_item=placeholder,
        relative_path=(
            "2067 (2020)/2067 (2020).mkv"
        ),
    )

    item = _movie_item(
        library=library,
        media_file=media_file,
        candidate=SemanticCandidate(
            kind="movie",
            title="2067",
            year=2020,
            source="folder",
            confidence=0.95,
        ),
    )

    title_state = (
        CanonicalFieldState.objects
        .get(
            target_type="media_item",
            target_id=item.id,
            field_name="title",
        )
    )

    year_state = (
        CanonicalFieldState.objects
        .get(
            target_type="media_item",
            target_id=item.id,
            field_name="year",
        )
    )

    assert title_state.source == "folder"
    assert title_state.locked is False
    assert title_state.value_snapshot == "2067"

    assert year_state.source == "folder"
    assert year_state.value_snapshot == 2020
