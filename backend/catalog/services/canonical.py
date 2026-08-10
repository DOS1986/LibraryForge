from __future__ import annotations

from copy import deepcopy
from typing import Any

from django.db import transaction

from catalog.models import (
    ArtworkFile,
    CanonicalFieldState,
    Episode,
    MediaVersion,
    MetadataChangeSet,
    Season,
    Series,
)
from media.models import MediaItem

from catalog.services.artwork import artwork_for_target
from metadata.models import (
    MetadataSource,
    NfoFile,
)


def _json_value(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()

    return deepcopy(value)


def field_states_for(
    *,
    target_type: str,
    target_id,
):
    return {
        state.field_name: state
        for state in (
            CanonicalFieldState.objects
            .filter(
                target_type=target_type,
                target_id=target_id,
            )
        )
    }


def is_field_locked(
    *,
    target_type: str,
    target_id,
    field_name: str,
):
    if not target_id:
        return False

    return (
        CanonicalFieldState.objects
        .filter(
            target_type=target_type,
            target_id=target_id,
            field_name=field_name,
            locked=True,
        )
        .exists()
    )


def set_field_provenance(
    *,
    target_type: str,
    target_id,
    field_name: str,
    source: str,
    value,
    source_ref: str = "",
):
    if not target_id:
        return None

    valid_sources = {
        source_value
        for source_value, _label
        in CanonicalFieldState.Source.choices
    }

    normalized_source = (
        source
        if source in valid_sources
        else CanonicalFieldState.Source.SYSTEM
    )

    snapshot = _json_value(
        value
    )

    state = (
        CanonicalFieldState.objects
        .filter(
            target_type=target_type,
            target_id=target_id,
            field_name=field_name,
        )
        .first()
    )

    if state and state.locked:
        return state

    if state:
        if (
            state.source
            == normalized_source
            and state.source_ref
            == source_ref
            and state.value_snapshot
            == snapshot
            and state.updated_by_id
            is None
        ):
            return state

        state.source = normalized_source
        state.source_ref = source_ref
        state.value_snapshot = snapshot
        state.locked = False
        state.updated_by = None

        state.save(
            update_fields=[
                "source",
                "source_ref",
                "value_snapshot",
                "locked",
                "updated_by",
                "updated_at",
            ]
        )

        return state

    return CanonicalFieldState.objects.create(
        target_type=target_type,
        target_id=target_id,
        field_name=field_name,
        source=normalized_source,
        source_ref=source_ref,
        value_snapshot=snapshot,
        locked=False,
    )


def _record_manual_changes(
    *,
    target_type: str,
    target_id,
    changes: dict[str, dict[str, Any]],
    user,
    note: str = "",
):
    if not changes:
        return None

    for field_name, values in changes.items():
        CanonicalFieldState.objects.update_or_create(
            target_type=target_type,
            target_id=target_id,
            field_name=field_name,
            defaults={
                "source": (
                    CanonicalFieldState
                    .Source
                    .MANUAL
                ),
                "value_snapshot": (
                    _json_value(
                        values.get("new")
                    )
                ),
                "locked": True,
                "updated_by": user,
            },
        )

    return MetadataChangeSet.objects.create(
        target_type=target_type,
        target_id=target_id,
        source=(
            MetadataChangeSet
            .Source
            .MANUAL
        ),
        changes={
            key: {
                "old": _json_value(
                    value.get("old")
                ),
                "new": _json_value(
                    value.get("new")
                ),
            }
            for key, value in changes.items()
        },
        note=note,
        changed_by=user,
    )


def _set_attr_changes(
    *,
    obj,
    values: dict[str, Any],
):
    changed = {}

    for field_name, new_value in values.items():
        old_value = getattr(
            obj,
            field_name,
        )

        if old_value == new_value:
            continue

        changed[field_name] = {
            "old": old_value,
            "new": new_value,
        }

        setattr(
            obj,
            field_name,
            new_value,
        )

    return changed


def _movie_year(
    media_item: MediaItem,
):
    return (
        media_item
        .canonical_metadata
        .get(
            "semantic",
            {},
        )
        .get(
            "year"
        )
    )


def _set_movie_year(
    *,
    media_item: MediaItem,
    year,
):
    canonical = dict(
        media_item.canonical_metadata
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

    semantic[
        "year"
    ] = year

    canonical[
        "semantic"
    ] = semantic

    media_item.canonical_metadata = canonical


def serialize_field_states(
    *,
    target_type: str,
    target_id,
):
    return [
        {
            "id": str(state.id),
            "target_type": state.target_type,
            "target_id": str(state.target_id),
            "field_name": state.field_name,
            "source": state.source,
            "source_label": state.get_source_display(),
            "source_ref": state.source_ref,
            "value_snapshot": state.value_snapshot,
            "locked": state.locked,
            "updated_by": (
                str(state.updated_by_id)
                if state.updated_by_id
                else None
            ),
            "created_at": state.created_at,
            "updated_at": state.updated_at,
        }
        for state in (
            CanonicalFieldState.objects
            .filter(
                target_type=target_type,
                target_id=target_id,
            )
            .select_related(
                "updated_by"
            )
            .order_by(
                "field_name"
            )
        )
    ]


def serialize_history(
    *,
    target_type: str,
    target_id,
    limit: int = 100,
):
    return [
        {
            "id": str(change.id),
            "target_type": change.target_type,
            "target_id": str(change.target_id),
            "source": change.source,
            "source_label": change.get_source_display(),
            "changes": change.changes,
            "note": change.note,
            "changed_by": (
                str(change.changed_by_id)
                if change.changed_by_id
                else None
            ),
            "changed_by_label": (
                getattr(
                    change.changed_by,
                    "email",
                    None,
                )
                if change.changed_by
                else None
            ),
            "created_at": change.created_at,
        }
        for change in (
            MetadataChangeSet.objects
            .filter(
                target_type=target_type,
                target_id=target_id,
            )
            .select_related(
                "changed_by"
            )
            .order_by(
                "-created_at"
            )[:limit]
        )
    ]


def _serialize_sources_for_media_item(
    media_item: MediaItem,
):
    return [
        {
            "id": str(source.id),
            "source_type": source.source_type,
            "source_type_label": (
                source.get_source_type_display()
            ),
            "status": source.status,
            "status_label": (
                source.get_status_display()
            ),
            "media_file_id": str(
                source.media_file_id
            ),
            "file_name": source.media_file.file_name,
            "relative_path": (
                source.media_file.relative_path
            ),
            "extracted_data": source.extracted_data,
            "error": source.error,
            "last_checked_at": source.last_checked_at,
        }
        for source in (
            MetadataSource.objects
            .filter(
                media_item=media_item,
            )
            .select_related(
                "media_file"
            )
            .order_by(
                "source_type",
                "media_file__relative_path",
            )
        )
    ]


def _serialize_nfos_for_media_item(
    media_item: MediaItem,
):
    return [
        {
            "id": str(nfo.id),
            "file_name": nfo.file_name,
            "relative_path": nfo.relative_path,
            "root_element": nfo.root_element,
            "title": nfo.title,
            "year": nfo.year,
            "raw_xml": nfo.raw_xml,
            "parsed_data": nfo.parsed_data,
            "parse_status": nfo.parse_status,
            "parse_error": nfo.parse_error,
            "is_generated": nfo.is_generated,
            "is_present": nfo.is_present,
            "updated_at": nfo.updated_at,
        }
        for nfo in (
            NfoFile.objects
            .filter(
                media_item=media_item,
                is_present=True,
            )
            .order_by(
                "relative_path"
            )
        )
    ]


def serialize_version(
    version: MediaVersion,
):
    media_file = version.media_file

    return {
        "id": str(version.id),
        "media_item_id": str(version.media_item_id),
        "file_id": str(version.media_file_id),
        "name": version.name,
        "edition": version.edition,
        "notes": version.notes,
        "is_primary": version.is_primary,
        "file_name": media_file.file_name,
        "relative_path": media_file.relative_path,
        "size_bytes": media_file.size_bytes,
        "duration_seconds": media_file.duration_seconds,
        "container_format": media_file.container_format,
        "bit_rate": media_file.bit_rate,
        "video_codec": media_file.video_codec,
        "width": media_file.width,
        "height": media_file.height,
        "audio_codec": media_file.audio_codec,
        "audio_channels": media_file.audio_channels,
        "metadata": version.metadata,
    }


def _versions_for_item(
    media_item: MediaItem,
):
    return [
        serialize_version(version)
        for version in (
            MediaVersion.objects
            .filter(
                media_item=media_item,
                media_file__is_present=True,
            )
            .select_related(
                "media_file"
            )
            .order_by(
                "-is_primary",
                "name",
            )
        )
    ]


def movie_detail(
    media_item: MediaItem,
):
    target_type = (
        CanonicalFieldState
        .TargetType
        .MEDIA_ITEM
    )

    return {
        "kind": "movie",
        "id": str(media_item.id),
        "library_id": str(media_item.library_id),
        "semantic_key": media_item.semantic_key,
        "semantic_locked": media_item.semantic_locked,
        "metadata": {
            "title": media_item.title,
            "sort_title": media_item.sort_title,
            "original_title": media_item.original_title,
            "year": _movie_year(media_item),
            "release_date": media_item.release_date,
            "description": media_item.description,
            "tagline": media_item.tagline,
            "content_rating": media_item.content_rating,
            "genres": media_item.genres,
            "studios": media_item.studios,
            "external_ids": media_item.external_ids,
        },
        "field_states": serialize_field_states(
            target_type=target_type,
            target_id=media_item.id,
        ),
        "versions": _versions_for_item(
            media_item
        ),
        "sources": _serialize_sources_for_media_item(
            media_item
        ),
        "nfo_files": _serialize_nfos_for_media_item(
            media_item
        ),
        "artwork": artwork_for_target(
            target_type=(
                ArtworkFile.TargetType.MEDIA_ITEM
            ),
            target_id=media_item.id,
        ),
        "history": serialize_history(
            target_type=target_type,
            target_id=media_item.id,
        ),
    }


def series_detail(
    series: Series,
):
    target_type = (
        CanonicalFieldState
        .TargetType
        .SERIES
    )

    return {
        "kind": "series",
        "id": str(series.id),
        "library_id": str(series.library_id),
        "semantic_key": series.semantic_key,
        "semantic_locked": series.locked,
        "metadata": {
            "title": series.title,
            "sort_title": series.sort_title,
            "original_title": series.original_title,
            "start_year": series.start_year,
            "end_year": series.end_year,
            "description": series.description,
            "tagline": series.tagline,
            "content_rating": series.content_rating,
            "genres": series.genres,
            "studios": series.studios,
            "external_ids": series.external_ids,
        },
        "field_states": serialize_field_states(
            target_type=target_type,
            target_id=series.id,
        ),
        "versions": [],
        "sources": [],
        "nfo_files": [],
        "artwork": artwork_for_target(
            target_type=(
                ArtworkFile.TargetType.SERIES
            ),
            target_id=series.id,
        ),
        "history": serialize_history(
            target_type=target_type,
            target_id=series.id,
        ),
    }


def season_detail(
    season: Season,
):
    target_type = (
        CanonicalFieldState
        .TargetType
        .SEASON
    )

    return {
        "kind": "season",
        "id": str(season.id),
        "library_id": str(season.series.library_id),
        "semantic_key": None,
        "semantic_locked": season.locked,
        "metadata": {
            "title": season.title,
            "season_number": season.season_number,
            "description": season.description,
            "external_ids": season.external_ids,
        },
        "field_states": serialize_field_states(
            target_type=target_type,
            target_id=season.id,
        ),
        "versions": [],
        "sources": [],
        "nfo_files": [],
        "artwork": artwork_for_target(
            target_type=(
                ArtworkFile.TargetType.SEASON
            ),
            target_id=season.id,
        ),
        "history": serialize_history(
            target_type=target_type,
            target_id=season.id,
        ),
    }


def episode_detail(
    episode: Episode,
):
    media_item = episode.media_item

    target_type = (
        CanonicalFieldState
        .TargetType
        .EPISODE
    )

    return {
        "kind": "episode",
        "id": str(episode.id),
        "media_item_id": str(media_item.id),
        "library_id": str(media_item.library_id),
        "semantic_key": media_item.semantic_key,
        "semantic_locked": episode.locked,
        "context": {
            "series_id": str(
                episode.season.series_id
            ),
            "series_title": (
                episode.season.series.title
            ),
            "season_id": str(
                episode.season_id
            ),
            "season_number": (
                episode.season.season_number
            ),
            "episode_number": episode.episode_number,
            "episode_end_number": (
                episode.episode_end_number
            ),
        },
        "metadata": {
            "title": media_item.title,
            "sort_title": media_item.sort_title,
            "original_title": media_item.original_title,
            "air_date": episode.air_date,
            "description": media_item.description,
            "content_rating": media_item.content_rating,
            "genres": media_item.genres,
            "studios": media_item.studios,
            "absolute_number": episode.absolute_number,
            "external_ids": episode.external_ids,
        },
        "field_states": serialize_field_states(
            target_type=target_type,
            target_id=episode.id,
        ),
        "versions": _versions_for_item(
            media_item
        ),
        "sources": _serialize_sources_for_media_item(
            media_item
        ),
        "nfo_files": _serialize_nfos_for_media_item(
            media_item
        ),
        "artwork": artwork_for_target(
            target_type=(
                ArtworkFile.TargetType.EPISODE
            ),
            target_id=episode.id,
        ),
        "history": serialize_history(
            target_type=target_type,
            target_id=episode.id,
        ),
    }


@transaction.atomic
def update_movie_metadata(
    *,
    media_item: MediaItem,
    values: dict[str, Any],
    user,
    note: str = "",
):
    target_type = (
        CanonicalFieldState
        .TargetType
        .MEDIA_ITEM
    )

    direct_fields = {
        key: value
        for key, value in values.items()
        if key in {
            "title",
            "sort_title",
            "original_title",
            "release_date",
            "description",
            "tagline",
            "content_rating",
            "genres",
            "studios",
            "external_ids",
        }
    }

    changes = _set_attr_changes(
        obj=media_item,
        values=direct_fields,
    )

    if "year" in values:
        old_year = _movie_year(
            media_item
        )

        new_year = values[
            "year"
        ]

        if old_year != new_year:
            changes[
                "year"
            ] = {
                "old": old_year,
                "new": new_year,
            }

            _set_movie_year(
                media_item=media_item,
                year=new_year,
            )

    if changes:
        media_item.save()

        _record_manual_changes(
            target_type=target_type,
            target_id=media_item.id,
            changes=changes,
            user=user,
            note=note,
        )

    return movie_detail(
        media_item
    )


@transaction.atomic
def update_series_metadata(
    *,
    series: Series,
    values: dict[str, Any],
    user,
    note: str = "",
):
    target_type = (
        CanonicalFieldState
        .TargetType
        .SERIES
    )

    direct_fields = {
        key: value
        for key, value in values.items()
        if key in {
            "title",
            "sort_title",
            "original_title",
            "start_year",
            "end_year",
            "description",
            "tagline",
            "content_rating",
            "genres",
            "studios",
            "external_ids",
        }
    }

    changes = _set_attr_changes(
        obj=series,
        values=direct_fields,
    )

    if changes:
        series.save()

        _record_manual_changes(
            target_type=target_type,
            target_id=series.id,
            changes=changes,
            user=user,
            note=note,
        )

    return series_detail(
        series
    )


@transaction.atomic
def update_season_metadata(
    *,
    season: Season,
    values: dict[str, Any],
    user,
    note: str = "",
):
    target_type = (
        CanonicalFieldState
        .TargetType
        .SEASON
    )

    direct_fields = {
        key: value
        for key, value in values.items()
        if key in {
            "title",
            "description",
            "external_ids",
        }
    }

    changes = _set_attr_changes(
        obj=season,
        values=direct_fields,
    )

    if changes:
        season.save()

        _record_manual_changes(
            target_type=target_type,
            target_id=season.id,
            changes=changes,
            user=user,
            note=note,
        )

    return season_detail(
        season
    )


@transaction.atomic
def update_episode_metadata(
    *,
    episode: Episode,
    values: dict[str, Any],
    user,
    note: str = "",
):
    target_type = (
        CanonicalFieldState
        .TargetType
        .EPISODE
    )

    media_item = episode.media_item

    item_fields = {
        key: value
        for key, value in values.items()
        if key in {
            "title",
            "sort_title",
            "original_title",
            "description",
            "content_rating",
            "genres",
            "studios",
        }
    }

    episode_fields = {
        key: value
        for key, value in values.items()
        if key in {
            "air_date",
            "absolute_number",
            "external_ids",
        }
    }

    changes = {}

    changes.update(
        _set_attr_changes(
            obj=media_item,
            values=item_fields,
        )
    )

    changes.update(
        _set_attr_changes(
            obj=episode,
            values=episode_fields,
        )
    )

    if changes:
        media_item.save()
        episode.save()

        _record_manual_changes(
            target_type=target_type,
            target_id=episode.id,
            changes=changes,
            user=user,
            note=note,
        )

    return episode_detail(
        episode
    )


@transaction.atomic
def update_media_version(
    *,
    version: MediaVersion,
    values: dict[str, Any],
    user,
    note: str = "",
):
    target_type = (
        CanonicalFieldState
        .TargetType
        .MEDIA_VERSION
    )

    direct_fields = {
        key: value
        for key, value in values.items()
        if key in {
            "name",
            "edition",
            "notes",
        }
    }

    changes = _set_attr_changes(
        obj=version,
        values=direct_fields,
    )

    if changes:
        version.save()

        _record_manual_changes(
            target_type=target_type,
            target_id=version.id,
            changes=changes,
            user=user,
            note=note,
        )

    return serialize_version(
        version
    )


@transaction.atomic
def make_primary_version(
    *,
    version: MediaVersion,
    user,
):
    media_item = version.media_item

    current_primary = (
        MediaVersion.objects
        .filter(
            media_item=media_item,
            is_primary=True,
        )
        .exclude(
            pk=version.pk
        )
        .first()
    )

    if version.is_primary and not current_primary:
        return serialize_version(
            version
        )

    changes = {}

    if current_primary:
        current_primary.is_primary = False
        current_primary.save(
            update_fields=[
                "is_primary",
                "updated_at",
            ]
        )

        _record_manual_changes(
            target_type=(
                CanonicalFieldState
                .TargetType
                .MEDIA_VERSION
            ),
            target_id=current_primary.id,
            changes={
                "is_primary": {
                    "old": True,
                    "new": False,
                }
            },
            user=user,
            note="Primary version changed.",
        )

    old_primary = version.is_primary

    version.is_primary = True
    version.save(
        update_fields=[
            "is_primary",
            "updated_at",
        ]
    )

    if old_primary is not True:
        changes[
            "is_primary"
        ] = {
            "old": old_primary,
            "new": True,
        }

    if changes:
        _record_manual_changes(
            target_type=(
                CanonicalFieldState
                .TargetType
                .MEDIA_VERSION
            ),
            target_id=version.id,
            changes=changes,
            user=user,
            note="Set as primary version.",
        )

    return serialize_version(
        version
    )
