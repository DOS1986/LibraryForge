from pathlib import Path

import pytest
from django.contrib.auth import get_user_model

from catalog.models import (
    ArtworkFile,
    Episode,
    MediaVersion,
    Season,
    Series,
)
from catalog.services.artwork import (
    scan_library_artwork,
    select_artwork,
)
from libraries.models import Library
from media.models import MediaFile, MediaItem


pytestmark = pytest.mark.django_db


def user():
    return get_user_model().objects.create_user(
        email="artwork@example.com",
        password="test-password",
    )


def library(tmp_path: Path, owner, content_type="movies"):
    return Library.objects.create(
        owner=owner,
        name="Artwork Test",
        path=str(tmp_path),
        content_type=content_type,
        management_mode="read_only",
    )


def add_movie(lib, relative_path):
    item = MediaItem.objects.create(
        library=lib,
        title="Blade Runner",
        media_type=MediaItem.MediaType.MOVIE,
        semantic_key="movie:blade-runner:1982",
    )

    media_file = MediaFile.objects.create(
        library=lib,
        media_item=item,
        relative_path=relative_path,
        file_name=Path(relative_path).name,
        extension="mkv",
        is_present=True,
    )

    MediaVersion.objects.create(
        media_item=item,
        media_file=media_file,
        name="1080p",
        is_primary=True,
    )

    return item


def test_movie_artwork_is_detected_and_preferred(tmp_path):
    owner = user()
    lib = library(tmp_path, owner)

    movie_dir = tmp_path / "Blade Runner (1982)"
    movie_dir.mkdir()

    add_movie(
        lib,
        "Blade Runner (1982)/Blade Runner (1982).mkv",
    )

    (movie_dir / "poster.jpg").write_bytes(b"poster")
    (movie_dir / "folder.jpg").write_bytes(b"folder")
    (movie_dir / "fanart.jpg").write_bytes(b"fanart")
    (movie_dir / "clearlogo.png").write_bytes(b"logo")

    result = scan_library_artwork(
        library=lib
    )

    assert result["error_count"] == 0
    assert ArtworkFile.objects.filter(
        library=lib,
        is_present=True,
    ).count() == 4

    primary = ArtworkFile.objects.get(
        library=lib,
        artwork_type="primary",
        is_selected=True,
    )

    assert primary.file_name == "poster.jpg"

    backdrop = ArtworkFile.objects.get(
        library=lib,
        artwork_type="backdrop",
        is_selected=True,
    )

    assert backdrop.file_name == "fanart.jpg"


def test_user_can_change_preferred_artwork(tmp_path):
    owner = user()
    lib = library(tmp_path, owner)

    movie_dir = tmp_path / "Blade Runner (1982)"
    movie_dir.mkdir()

    add_movie(
        lib,
        "Blade Runner (1982)/Blade Runner (1982).mkv",
    )

    (movie_dir / "poster.jpg").write_bytes(b"poster")
    (movie_dir / "folder.jpg").write_bytes(b"folder")

    scan_library_artwork(
        library=lib
    )

    folder = ArtworkFile.objects.get(
        library=lib,
        file_name="folder.jpg",
    )

    select_artwork(
        artwork=folder,
        user=owner,
    )

    folder.refresh_from_db()

    assert folder.is_selected is True

    poster = ArtworkFile.objects.get(
        library=lib,
        file_name="poster.jpg",
    )

    assert poster.is_selected is False


def test_tv_series_season_and_episode_artwork(tmp_path):
    owner = user()
    lib = library(
        tmp_path,
        owner,
        content_type="tv",
    )

    series = Series.objects.create(
        library=lib,
        title="The Expanse",
        semantic_key="series:the-expanse:2015",
        start_year=2015,
    )

    season = Season.objects.create(
        series=series,
        season_number=1,
        title="Season 1",
    )

    item = MediaItem.objects.create(
        library=lib,
        title="Dulcinea",
        media_type=MediaItem.MediaType.TV_EPISODE,
        semantic_key=(
            "episode:series:the-expanse:2015:s0001e0001"
        ),
    )

    episode = Episode.objects.create(
        media_item=item,
        season=season,
        episode_number=1,
    )

    relative = (
        "The Expanse/Season 01/"
        "The Expanse S01E01.mkv"
    )

    media_file = MediaFile.objects.create(
        library=lib,
        media_item=item,
        relative_path=relative,
        file_name="The Expanse S01E01.mkv",
        extension="mkv",
        is_present=True,
    )

    MediaVersion.objects.create(
        media_item=item,
        media_file=media_file,
        name="Default",
        is_primary=True,
    )

    series_dir = tmp_path / "The Expanse"
    season_dir = series_dir / "Season 01"
    season_dir.mkdir(parents=True)

    (series_dir / "poster.jpg").write_bytes(b"series")
    (season_dir / "poster.jpg").write_bytes(b"season")
    (
        season_dir
        / "The Expanse S01E01-thumb.jpg"
    ).write_bytes(b"episode")

    scan_library_artwork(
        library=lib
    )

    assert ArtworkFile.objects.filter(
        target_type="series",
        target_id=series.id,
        artwork_type="primary",
    ).exists()

    assert ArtworkFile.objects.filter(
        target_type="season",
        target_id=season.id,
        artwork_type="primary",
    ).exists()

    assert ArtworkFile.objects.filter(
        target_type="episode",
        target_id=episode.id,
        artwork_type="primary",
    ).exists()


def test_missing_artwork_is_reconciled_safely(tmp_path):
    owner = user()
    lib = library(tmp_path, owner)

    movie_dir = tmp_path / "Blade Runner (1982)"
    movie_dir.mkdir()

    add_movie(
        lib,
        "Blade Runner (1982)/Blade Runner (1982).mkv",
    )

    poster_path = movie_dir / "poster.jpg"
    poster_path.write_bytes(b"poster")

    scan_library_artwork(
        library=lib
    )

    poster_path.unlink()

    scan_library_artwork(
        library=lib
    )

    artwork = ArtworkFile.objects.get(
        library=lib,
        file_name="poster.jpg",
    )

    assert artwork.is_present is False
    assert artwork.is_selected is False
