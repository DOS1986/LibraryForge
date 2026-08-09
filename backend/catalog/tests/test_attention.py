import pytest

from django.contrib.auth import (
    get_user_model,
)

from catalog.models import (
    MediaVersion,
    SemanticMatch,
)

from catalog.services.parser import (
    SemanticCandidate,
)

from catalog.services.resolver import (
    apply_manual_resolution,
    reset_semantic_match,
    set_semantic_match_lock,
)

from libraries.models import Library

from media.models import (
    MediaFile,
    MediaItem,
)


pytestmark = pytest.mark.django_db


def create_file(
    *,
    content_type,
    relative_path,
):
    user = (
        get_user_model()
        .objects
        .create_user(
            email=(
                f"{content_type}@example.com"
            ),
            password="test-password",
        )
    )

    library = Library.objects.create(
        owner=user,
        name=(
            f"{content_type} library"
        ),
        path=(
            f"/library/{content_type}"
        ),
        content_type=content_type,
    )

    item = MediaItem.objects.create(
        library=library,
        title=(
            "Temporary physical title"
        ),
    )

    media_file = (
        MediaFile.objects.create(
            library=library,
            media_item=item,
            relative_path=(
                relative_path
            ),
            file_name=(
                relative_path
                .rsplit(
                    "/",
                    1,
                )[-1]
            ),
            extension="mkv",
            size_bytes=1000,
            duration_seconds=120,
            probe_status=(
                MediaFile
                .ProbeStatus
                .OK
            ),
        )
    )

    match = (
        SemanticMatch.objects.create(
            media_file=media_file,
            status=(
                SemanticMatch
                .Status
                .UNRESOLVED
            ),
            confidence=0.4,
            candidate_data={},
        )
    )

    return (
        library,
        media_file,
        match,
    )


def test_manual_movie_resolution_locks_file():
    (
        _library,
        media_file,
        match,
    ) = create_file(
        content_type="movies",
        relative_path=(
            "Blade Runner (1982)/"
            "Blade Runner Final Cut.mkv"
        ),
    )

    candidate = SemanticCandidate(
        kind="movie",
        title="Blade Runner",
        year=1982,
        edition="Final Cut",
        source="manual",
        confidence=1.0,
    )

    updated = (
        apply_manual_resolution(
            match=match,
            candidate=candidate,
            lock=True,
            notes="Confirmed by user.",
        )
    )

    media_file.refresh_from_db()

    assert updated.status == (
        SemanticMatch
        .Status
        .MANUAL
    )

    assert updated.locked is True

    assert (
        media_file
        .media_item
        .media_type
        == MediaItem
        .MediaType
        .MOVIE
    )

    assert (
        media_file
        .media_item
        .title
        == "Blade Runner"
    )

    version = (
        MediaVersion.objects
        .get(
            media_file=media_file
        )
    )

    assert (
        version.edition
        == "Final Cut"
    )


def test_unlock_keeps_assignment():
    (
        _library,
        media_file,
        match,
    ) = create_file(
        content_type="movies",
        relative_path=(
            "Alien (1979)/Alien.mkv"
        ),
    )

    updated = (
        apply_manual_resolution(
            match=match,
            candidate=(
                SemanticCandidate(
                    kind="movie",
                    title="Alien",
                    year=1979,
                    source="manual",
                    confidence=1.0,
                )
            ),
            lock=True,
        )
    )

    set_semantic_match_lock(
        match=updated,
        locked=False,
    )

    media_file.refresh_from_db()

    assert (
        media_file
        .media_item
        .title
        == "Alien"
    )

    updated.refresh_from_db()

    assert updated.locked is False


def test_reset_reruns_automatic_resolver():
    (
        _library,
        media_file,
        match,
    ) = create_file(
        content_type="movies",
        relative_path=(
            "Blade Runner (1982)/"
            "Blade Runner Final Cut.mkv"
        ),
    )

    manual = (
        apply_manual_resolution(
            match=match,
            candidate=(
                SemanticCandidate(
                    kind="movie",
                    title="Wrong Title",
                    year=2000,
                    source="manual",
                    confidence=1.0,
                )
            ),
            lock=True,
        )
    )

    (
        reset_match,
        result,
    ) = reset_semantic_match(
        match=manual
    )

    media_file.refresh_from_db()

    assert result == "matched"

    assert (
        reset_match.status
        == SemanticMatch
        .Status
        .MATCHED
    )

    assert (
        reset_match.locked
        is False
    )

    assert (
        media_file
        .media_item
        .title
        == "Blade Runner"
    )
