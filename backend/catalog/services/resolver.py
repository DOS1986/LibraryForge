from django.db import transaction
from django.utils import timezone

from catalog.models import (
    Episode,
    MediaVersion,
    Season,
    SemanticMatch,
    Series,
)

from catalog.services.canonical import (
    is_field_locked,
    set_field_provenance,
)

from catalog.services.parser import (
    SemanticCandidate,
    build_version_name,
    episode_semantic_key,
    identities_conflict,
    identity_text_key,
    movie_semantic_key,
    parse_filename_candidate,
    parse_nfo_candidate,
    series_semantic_key,
)

from media.models import (
    MediaFile,
    MediaItem,
)

from metadata.models import (
    MetadataSource,
    NfoFile,
)


def _candidate_allowed(
    library,
    candidate: SemanticCandidate,
):
    if candidate.kind == "unknown":
        return False

    content_type = (
        library.content_type
    )

    if content_type == "movies":
        return (
            candidate.kind
            == "movie"
            and candidate.confidence
            >= 0.70
        )

    if content_type == "tv":
        return (
            candidate.kind
            == "episode"
            and candidate.confidence
            >= 0.85
        )

    if content_type in {
        "auto",
        "mixed",
    }:
        return (
            candidate.kind
            in {
                "movie",
                "episode",
            }
            and candidate.confidence
            >= 0.85
        )

    return False


def _update_match(
    media_file,
    *,
    status,
    source="",
    confidence=0.0,
    candidate_data=None,
    notes="",
):
    match, _created = (
        SemanticMatch.objects
        .get_or_create(
            media_file=media_file
        )
    )

    if match.locked:
        return match

    match.status = status
    match.source = source
    match.confidence = confidence
    match.candidate_data = (
        candidate_data
        or {}
    )
    match.notes = notes
    match.last_resolved_at = (
        timezone.now()
    )

    match.save()

    return match


def _can_reuse_media_item(
    media_file,
):
    item = media_file.media_item

    if item.semantic_locked:
        return False

    if item.semantic_key:
        return False

    if (
        item.files
        .filter(
            is_present=True
        )
        .exclude(
            id=media_file.id
        )
        .exists()
    ):
        return False

    if (
        Episode.objects
        .filter(
            media_item=item
        )
        .exists()
    ):
        return False

    if (
        MediaVersion.objects
        .filter(
            media_item=item
        )
        .exists()
    ):
        return False

    return True


def _delete_orphan_placeholder(
    media_item,
):
    if media_item.semantic_key:
        return

    if media_item.semantic_locked:
        return

    if media_item.files.exists():
        return

    if (
        Episode.objects
        .filter(
            media_item=media_item
        )
        .exists()
    ):
        return

    if (
        MediaVersion.objects
        .filter(
            media_item=media_item
        )
        .exists()
    ):
        return

    media_item.delete()


def _move_media_file(
    media_file,
    media_item,
):
    if (
        media_file.media_item_id
        == media_item.id
    ):
        return

    old_item = (
        media_file.media_item
    )

    media_file.media_item = (
        media_item
    )

    media_file.save(
        update_fields=[
            "media_item",
            "updated_at",
        ]
    )

    MetadataSource.objects.filter(
        media_file=media_file
    ).update(
        media_item=media_item
    )

    NfoFile.objects.filter(
        media_file=media_file
    ).update(
        media_item=media_item
    )

    _delete_orphan_placeholder(
        old_item
    )


def _detach_semantic_assignment(
    media_file,
):
    version = (
        MediaVersion.objects
        .filter(
            media_file=media_file
        )
        .first()
    )

    if version:
        version.delete()

    current_item = (
        media_file.media_item
    )

    if not current_item.semantic_key:
        return

    placeholder = (
        MediaItem.objects.create(
            library=(
                media_file.library
            ),
            title=(
                media_file.file_name
                .rsplit(
                    ".",
                    1,
                )[0]
            ),
            media_type=(
                MediaItem
                .MediaType
                .UNKNOWN
            ),
        )
    )

    _move_media_file(
        media_file,
        placeholder,
    )


def _ensure_version(
    *,
    media_file,
    media_item,
    edition="",
):
    version = (
        MediaVersion.objects
        .filter(
            media_file=media_file
        )
        .first()
    )

    technical_metadata = {
        "video_codec":
            media_file.video_codec,

        "width":
            media_file.width,

        "height":
            media_file.height,

        "container_format":
            media_file.container_format,

        "bit_rate":
            media_file.bit_rate,

        "audio_codec":
            media_file.audio_codec,

        "audio_channels":
            media_file.audio_channels,
    }

    if version:
        version.media_item = media_item
        version.metadata = technical_metadata

        if not is_field_locked(
            target_type="media_version",
            target_id=version.id,
            field_name="name",
        ):
            version.name = (
                build_version_name(
                    media_file
                )
            )

        if (
            edition
            and not is_field_locked(
                target_type="media_version",
                target_id=version.id,
                field_name="edition",
            )
        ):
            version.edition = edition

        version.save()

        return version

    other_primary_exists = (
        MediaVersion.objects
        .filter(
            media_item=media_item,
            is_primary=True,
        )
        .exists()
    )

    return MediaVersion.objects.create(
        media_file=media_file,
        media_item=media_item,
        name=build_version_name(
            media_file
        ),
        edition=edition,
        is_primary=(
            not other_primary_exists
        ),
        metadata=technical_metadata,
    )


def _movie_item(
    *,
    library,
    media_file,
    candidate,
):
    semantic_key = (
        movie_semantic_key(
            candidate.title,
            candidate.year,
        )
    )

    existing = (
        MediaItem.objects
        .filter(
            library=library,
            media_type=(
                MediaItem
                .MediaType
                .MOVIE
            ),
            semantic_key=semantic_key,
        )
        .first()
    )

    if existing:
        item = existing

    elif _can_reuse_media_item(
        media_file
    ):
        item = (
            media_file
            .media_item
        )

        item.media_type = (
            MediaItem
            .MediaType
            .MOVIE
        )

        item.semantic_key = (
            semantic_key
        )

    else:
        item = MediaItem(
            library=library,
            media_type=(
                MediaItem
                .MediaType
                .MOVIE
            ),
            semantic_key=(
                semantic_key
            ),
        )

    if not item.semantic_locked:
        if not (
            item.pk
            and is_field_locked(
                target_type="media_item",
                target_id=item.id,
                field_name="title",
            )
        ):
            item.title = (
                candidate.title
            )

        canonical = dict(
            item.canonical_metadata
            or {}
        )

        semantic = dict(
            canonical.get(
                "semantic",
                {},
            )
        )

        semantic[
            "kind"
        ] = "movie"

        if not (
            item.pk
            and is_field_locked(
                target_type="media_item",
                target_id=item.id,
                field_name="year",
            )
        ):
            semantic[
                "year"
            ] = candidate.year

        canonical[
            "semantic"
        ] = semantic

        item.canonical_metadata = (
            canonical
        )

    item.save()

    if not is_field_locked(
        target_type="media_item",
        target_id=item.id,
        field_name="title",
    ):
        set_field_provenance(
            target_type="media_item",
            target_id=item.id,
            field_name="title",
            source=candidate.source,
            value=item.title,
        )

    if not is_field_locked(
        target_type="media_item",
        target_id=item.id,
        field_name="year",
    ):
        set_field_provenance(
            target_type="media_item",
            target_id=item.id,
            field_name="year",
            source=candidate.source,
            value=(
                item.canonical_metadata
                .get(
                    "semantic",
                    {},
                )
                .get(
                    "year"
                )
            ),
        )

    _move_media_file(
        media_file,
        item,
    )

    _ensure_version(
        media_file=media_file,
        media_item=item,
        edition=(
            candidate.edition
        ),
    )

    return item


def _series_object(
    *,
    library,
    candidate,
):
    requested_key = (
        series_semantic_key(
            candidate.series_title,
            candidate.series_year,
        )
    )

    exact = (
        Series.objects
        .filter(
            library=library,
            semantic_key=requested_key,
        )
        .first()
    )

    if exact:
        series = exact

    else:
        normalized_title = (
            identity_text_key(
                candidate.series_title
            )
        )

        compatible = []

        for existing in (
            Series.objects
            .filter(
                library=library
            )
        ):
            if (
                identity_text_key(
                    existing.title
                )
                != normalized_title
            ):
                continue

            # Different known years mean different series/reboots.
            if (
                candidate.series_year
                and existing.start_year
                and candidate.series_year
                != existing.start_year
            ):
                continue

            compatible.append(
                existing
            )

        # A missing year is compatible with one existing series of the same
        # normalized title. If more than one reboot exists, keep an unknown
        # identity separate rather than guessing.
        if len(compatible) == 1:
            series = compatible[0]

        else:
            series = Series.objects.create(
                library=library,
                title=(
                    candidate
                    .series_title
                ),
                sort_title=(
                    candidate
                    .series_title
                ),
                semantic_key=(
                    requested_key
                ),
                start_year=(
                    candidate
                    .series_year
                ),
            )

    if not series.locked:
        changed_fields = []

        # Keep the clean NFO/folder display title. Punctuation differences
        # do not require creating a new logical Series.
        if (
            candidate.series_title
            and not is_field_locked(
                target_type="series",
                target_id=series.id,
                field_name="title",
            )
            and identity_text_key(
                series.title
            )
            == identity_text_key(
                candidate.series_title
            )
            and series.title
            != candidate.series_title
        ):
            # Prefer an existing human-readable title unless it still carries
            # a decorative year while the new parsed title does not.
            if (
                str(
                    series.start_year
                    or ""
                )
                in series.title
                and (
                    not candidate.series_year
                    or str(
                        candidate.series_year
                    )
                    not in candidate.series_title
                )
            ):
                series.title = (
                    candidate
                    .series_title
                )

                changed_fields.append(
                    "title"
                )

                if not is_field_locked(
                    target_type="series",
                    target_id=series.id,
                    field_name="sort_title",
                ):
                    series.sort_title = (
                        candidate
                        .series_title
                    )

                    changed_fields.append(
                        "sort_title"
                    )

        if (
            candidate.series_year
            and not series.start_year
            and not is_field_locked(
                target_type="series",
                target_id=series.id,
                field_name="start_year",
            )
        ):
            series.start_year = (
                candidate
                .series_year
            )

            changed_fields.append(
                "start_year"
            )

            upgraded_key = (
                series_semantic_key(
                    series.title,
                    candidate.series_year,
                )
            )

            key_in_use = (
                Series.objects
                .filter(
                    library=library,
                    semantic_key=(
                        upgraded_key
                    ),
                )
                .exclude(
                    pk=series.pk
                )
                .exists()
            )

            if not key_in_use:
                series.semantic_key = (
                    upgraded_key
                )

                changed_fields.append(
                    "semantic_key"
                )

        if changed_fields:
            changed_fields.append(
                "updated_at"
            )

            series.save(
                update_fields=(
                    list(
                        dict.fromkeys(
                            changed_fields
                        )
                    )
                )
            )

    if not is_field_locked(
        target_type="series",
        target_id=series.id,
        field_name="title",
    ):
        set_field_provenance(
            target_type="series",
            target_id=series.id,
            field_name="title",
            source=candidate.source,
            value=series.title,
        )

    if (
        candidate.series_year
        and not is_field_locked(
            target_type="series",
            target_id=series.id,
            field_name="start_year",
        )
    ):
        set_field_provenance(
            target_type="series",
            target_id=series.id,
            field_name="start_year",
            source=candidate.source,
            value=series.start_year,
        )

    return (
        series,
        series.semantic_key,
    )


def _episode_item(
    *,
    library,
    media_file,
    candidate,
):
    (
        series,
        series_key,
    ) = _series_object(
        library=library,
        candidate=candidate,
    )

    season_number = (
        candidate.season_number
    )

    episode_number = (
        candidate.episode_number
    )

    season, _created = (
        Season.objects
        .get_or_create(
            series=series,
            season_number=(
                season_number
            ),
            defaults={
                "title":
                    (
                        "Specials"
                        if season_number
                        == 0
                        else (
                            "Season "
                            f"{season_number}"
                        )
                    )
            },
        )
    )

    existing_episode = (
        Episode.objects
        .select_related(
            "media_item"
        )
        .filter(
            season=season,
            episode_number=(
                episode_number
            ),
        )
        .first()
    )

    semantic_key = (
        episode_semantic_key(
            series_key,
            season_number,
            episode_number,
        )
    )

    if existing_episode:
        item = (
            existing_episode
            .media_item
        )

        episode = (
            existing_episode
        )

    else:
        if _can_reuse_media_item(
            media_file
        ):
            item = (
                media_file
                .media_item
            )

            item.media_type = (
                MediaItem
                .MediaType
                .TV_EPISODE
            )

            item.semantic_key = (
                semantic_key
            )

        else:
            item = MediaItem(
                library=library,
                media_type=(
                    MediaItem
                    .MediaType
                    .TV_EPISODE
                ),
                semantic_key=(
                    semantic_key
                ),
            )

        item.title = (
            candidate.episode_title
            or candidate.title
            or (
                "Episode "
                f"{episode_number}"
            )
        )

        item.save()

        episode = Episode.objects.create(
            media_item=item,
            season=season,
            episode_number=(
                episode_number
            ),
            episode_end_number=(
                candidate
                .episode_end_number
            ),
        )

    if not item.semantic_locked:
        desired_title = (
            candidate.episode_title
            or candidate.title
        )

        if (
            desired_title
            and not is_field_locked(
                target_type="episode",
                target_id=episode.id,
                field_name="title",
            )
        ):
            item.title = (
                desired_title
            )

        canonical = dict(
            item.canonical_metadata
            or {}
        )

        canonical[
            "semantic"
        ] = {
            "kind":
                "episode",

            "series":
                series.title,

            "series_id":
                str(series.id),

            "season_number":
                season_number,

            "episode_number":
                episode_number,

            "episode_end_number":
                candidate
                .episode_end_number,
        }

        item.canonical_metadata = (
            canonical
        )

        item.save()

    if not is_field_locked(
        target_type="episode",
        target_id=episode.id,
        field_name="title",
    ):
        set_field_provenance(
            target_type="episode",
            target_id=episode.id,
            field_name="title",
            source=candidate.source,
            value=item.title,
        )

    if (
        candidate
        .episode_end_number
        and not episode.locked
        and episode.episode_end_number
        != candidate.episode_end_number
        and not is_field_locked(
            target_type="episode",
            target_id=episode.id,
            field_name="episode_end_number",
        )
    ):
        episode.episode_end_number = (
            candidate
            .episode_end_number
        )

        episode.save(
            update_fields=[
                "episode_end_number",
                "updated_at",
            ]
        )

    _move_media_file(
        media_file,
        item,
    )

    _ensure_version(
        media_file=media_file,
        media_item=item,
    )

    return item


def _best_nfo_for_file(
    nfo_files,
):
    for nfo in nfo_files:
        if (
            nfo.parse_status
            == NfoFile
            .ParseStatus
            .OK
            and nfo.root_element
            in {
                "movie",
                "episodedetails",
            }
        ):
            return nfo

    return None


def resolve_media_file(
    *,
    library,
    media_file,
    nfo_files,
):
    existing_match = (
        SemanticMatch.objects
        .filter(
            media_file=media_file
        )
        .first()
    )

    if (
        existing_match
        and existing_match.locked
    ):
        return "locked"

    filename_candidate = (
        parse_filename_candidate(
            relative_path=(
                media_file
                .relative_path
            ),
            library_content_type=(
                library
                .content_type
            ),
        )
    )

    nfo = _best_nfo_for_file(
        nfo_files
    )

    nfo_candidate = (
        parse_nfo_candidate(
            nfo
        )
        if nfo
        else SemanticCandidate()
    )

    if (
        nfo_candidate.kind
        != "unknown"
        and filename_candidate.kind
        != "unknown"
        and identities_conflict(
            nfo_candidate,
            filename_candidate,
        )
    ):
        _detach_semantic_assignment(
            media_file
        )

        _update_match(
            media_file,
            status=(
                SemanticMatch
                .Status
                .CONFLICT
            ),
            source=(
                SemanticMatch
                .Source
                .NFO
            ),
            confidence=(
                nfo_candidate
                .confidence
            ),
            candidate_data={
                "nfo":
                    nfo_candidate
                    .to_dict(),

                "filename":
                    filename_candidate
                    .to_dict(),
            },
            notes=(
                "NFO identity conflicts "
                "with filename/folder identity."
            ),
        )

        return "conflict"

    candidate = (
        nfo_candidate
        if (
            nfo_candidate.kind
            != "unknown"
        )
        else filename_candidate
    )

    if not _candidate_allowed(
        library,
        candidate,
    ):
        _detach_semantic_assignment(
            media_file
        )

        _update_match(
            media_file,
            status=(
                SemanticMatch
                .Status
                .UNRESOLVED
            ),
            source=(
                candidate.source
                or ""
            ),
            confidence=(
                candidate.confidence
            ),
            candidate_data=(
                candidate.to_dict()
            ),
            notes=(
                "No confident semantic "
                "movie/episode identity."
            ),
        )

        return "unresolved"

    with transaction.atomic():
        if candidate.kind == "movie":
            _movie_item(
                library=library,
                media_file=media_file,
                candidate=candidate,
            )

        elif candidate.kind == "episode":
            _episode_item(
                library=library,
                media_file=media_file,
                candidate=candidate,
            )

        else:
            return "unresolved"

        _update_match(
            media_file,
            status=(
                SemanticMatch
                .Status
                .MATCHED
            ),
            source=(
                (
                    SemanticMatch
                    .Source
                    .NFO
                )
                if (
                    candidate.source
                    == "nfo"
                )
                else (
                    SemanticMatch
                    .Source
                    .FOLDER
                    if (
                        candidate.source
                        == "folder"
                    )
                    else (
                        SemanticMatch
                        .Source
                        .FILENAME
                    )
                )
            ),
            confidence=(
                candidate.confidence
            ),
            candidate_data=(
                candidate.to_dict()
            ),
        )

    return "matched"


def resolve_library_semantics(
    *,
    library,
):
    if (
        library.content_type
        not in {
            "movies",
            "tv",
            "auto",
            "mixed",
        }
    ):
        return {
            "matched":
                0,

            "unresolved":
                0,

            "conflict":
                0,

            "locked":
                0,

            "error_count":
                0,

            "errors":
                [],
        }

    media_files = list(
        MediaFile.objects
        .filter(
            library=library,
            is_present=True,
        )
        .select_related(
            "media_item"
        )
    )

    nfo_map = {}

    for nfo in (
        NfoFile.objects
        .filter(
            library=library,
            is_present=True,
            media_file__isnull=False,
        )
        .order_by(
            "relative_path"
        )
    ):
        nfo_map.setdefault(
            nfo.media_file_id,
            [],
        ).append(
            nfo
        )

    result = {
        "matched":
            0,

        "unresolved":
            0,

        "conflict":
            0,

        "locked":
            0,

        "error_count":
            0,

        "errors":
            [],
    }

    for media_file in media_files:
        try:
            status = resolve_media_file(
                library=library,
                media_file=media_file,
                nfo_files=nfo_map.get(
                    media_file.id,
                    [],
                ),
            )

            if status in result:
                result[
                    status
                ] += 1

        except Exception as exc:
            result[
                "error_count"
            ] += 1

            if (
                len(
                    result[
                        "errors"
                    ]
                )
                < 100
            ):
                result[
                    "errors"
                ].append(
                    {
                        "path":
                            media_file
                            .relative_path,

                        "error":
                            str(exc),
                    }
                )

    return result


def _semantic_source_for_candidate(
    candidate: SemanticCandidate,
):
    if candidate.source == "nfo":
        return (
            SemanticMatch
            .Source
            .NFO
        )

    if candidate.source == "folder":
        return (
            SemanticMatch
            .Source
            .FOLDER
        )

    if candidate.source == "filename":
        return (
            SemanticMatch
            .Source
            .FILENAME
        )

    return (
        SemanticMatch
        .Source
        .MANUAL
    )


def _refresh_media_item_lock(
    media_item,
):
    locked = (
        SemanticMatch.objects
        .filter(
            media_file__media_item=(
                media_item
            ),
            locked=True,
        )
        .exists()
    )

    if (
        media_item.semantic_locked
        != locked
    ):
        media_item.semantic_locked = (
            locked
        )

        media_item.save(
            update_fields=[
                "semantic_locked",
                "updated_at",
            ]
        )

    try:
        episode = media_item.episode

    except Episode.DoesNotExist:
        episode = None

    if (
        episode
        and episode.locked
        != locked
    ):
        episode.locked = locked

        episode.save(
            update_fields=[
                "locked",
                "updated_at",
            ]
        )


def candidate_from_dict(
    data,
):
    if not isinstance(
        data,
        dict,
    ):
        return SemanticCandidate()

    allowed_fields = {
        "kind",
        "title",
        "year",
        "series_title",
        "series_year",
        "season_number",
        "episode_number",
        "episode_end_number",
        "episode_title",
        "edition",
        "source",
        "confidence",
    }

    values = {
        key:
            value
        for (
            key,
            value,
        )
        in data.items()
        if key
        in allowed_fields
    }

    try:
        return SemanticCandidate(
            **values
        )

    except TypeError:
        return SemanticCandidate()


def get_match_candidate(
    match,
    candidate_source: str,
):
    data = (
        match.candidate_data
        or {}
    )

    if candidate_source in {
        "nfo",
        "filename",
    }:
        candidate = candidate_from_dict(
            data.get(
                candidate_source
            )
        )

    elif (
        candidate_source
        == "suggested"
    ):
        candidate = candidate_from_dict(
            data.get(
                "selected"
            )
            or data
        )

    else:
        candidate = SemanticCandidate()

    return candidate


def apply_manual_resolution(
    *,
    match,
    candidate: SemanticCandidate,
    lock=True,
    notes="",
):
    media_file = (
        match.media_file
    )

    library = (
        media_file.library
    )

    if candidate.kind not in {
        "movie",
        "episode",
    }:
        raise ValueError(
            "Manual resolution must identify "
            "a movie or TV episode."
        )

    if (
        candidate.kind
        == "movie"
        and not candidate.title
    ):
        raise ValueError(
            "Movie title is required."
        )

    if (
        candidate.kind
        == "episode"
        and (
            not candidate.series_title
            or candidate.season_number
            is None
            or candidate.episode_number
            is None
        )
    ):
        raise ValueError(
            "Series title, season number, "
            "and episode number are required."
        )

    previous_candidates = (
        match.candidate_data
        or {}
    )

    previous_item = (
        media_file.media_item
    )

    with transaction.atomic():
        # An explicit user action is allowed to replace a previous lock.
        if match.locked:
            match.locked = False

            match.save(
                update_fields=[
                    "locked",
                    "updated_at",
                ]
            )

        _refresh_media_item_lock(
            previous_item
        )

        _detach_semantic_assignment(
            media_file
        )

        if candidate.kind == "movie":
            media_item = _movie_item(
                library=library,
                media_file=media_file,
                candidate=candidate,
            )

        else:
            media_item = _episode_item(
                library=library,
                media_file=media_file,
                candidate=candidate,
            )

        match.refresh_from_db()

        match.status = (
            SemanticMatch
            .Status
            .MANUAL
        )

        match.source = (
            _semantic_source_for_candidate(
                candidate
            )
        )

        match.confidence = 1.0

        match.candidate_data = {
            "selected":
                candidate.to_dict(),

            "previous":
                previous_candidates,
        }

        match.locked = bool(
            lock
        )

        match.notes = notes

        match.last_resolved_at = (
            timezone.now()
        )

        match.save()

        _refresh_media_item_lock(
            media_item
        )

    return match


def set_semantic_match_lock(
    *,
    match,
    locked: bool,
):
    media_item = (
        match.media_file
        .media_item
    )

    match.locked = bool(
        locked
    )

    match.save(
        update_fields=[
            "locked",
            "updated_at",
        ]
    )

    _refresh_media_item_lock(
        media_item
    )

    return match


def reset_semantic_match(
    *,
    match,
):
    media_file = (
        match.media_file
    )

    previous_item = (
        media_file.media_item
    )

    with transaction.atomic():
        match.locked = False

        match.save(
            update_fields=[
                "locked",
                "updated_at",
            ]
        )

        _refresh_media_item_lock(
            previous_item
        )

        _detach_semantic_assignment(
            media_file
        )

        nfo_files = list(
            NfoFile.objects
            .filter(
                media_file=media_file,
                is_present=True,
            )
            .order_by(
                "relative_path"
            )
        )

        result = resolve_media_file(
            library=(
                media_file.library
            ),
            media_file=media_file,
            nfo_files=nfo_files,
        )

    refreshed = (
        SemanticMatch.objects
        .select_related(
            "media_file",
            "media_file__media_item",
            "media_file__library",
        )
        .get(
            pk=match.pk
        )
    )

    return (
        refreshed,
        result,
    )

