from __future__ import annotations

import os
import re
from collections import defaultdict
from pathlib import Path, PurePosixPath

from django.db import transaction
from django.utils import timezone

from catalog.models import (
    ArtworkFile,
    Episode,
    MediaVersion,
    MetadataChangeSet,
)
from libraries.services.storage import validate_storage_path
from media.models import MediaItem


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}

SEASON_FOLDER_RE = re.compile(
    r"^(?:season[ ._-]*|s)(?P<number>\d{1,4})$",
    re.IGNORECASE,
)

SPECIALS_FOLDER_NAMES = {
    "special",
    "specials",
    "extras",
}

ARTWORK_RULES = {
    "primary": {
        "poster": 10,
        "folder": 20,
        "cover": 30,
        "default": 40,
        "movie": 50,
        "show": 50,
    },
    "backdrop": {
        "backdrop": 10,
        "fanart": 20,
        "background": 30,
        "art": 40,
    },
    "banner": {
        "banner": 10,
    },
    "logo": {
        "logo": 10,
        "clearlogo": 20,
    },
    "thumb": {
        "thumb": 10,
        "landscape": 20,
    },
}


def _season_folder_number(name: str):
    normalized = (name or "").strip().casefold()

    if normalized in SPECIALS_FOLDER_NAMES:
        return 0

    match = SEASON_FOLDER_RE.match(normalized)

    if not match:
        return None

    return int(match.group("number"))


def _normalized_stem(value: str):
    return (value or "").strip().casefold()


def _artwork_token(stem: str):
    value = _normalized_stem(stem)

    backdrop_match = re.fullmatch(
        r"backdrop(?:-?\d+)?",
        value,
    )

    if backdrop_match:
        return "backdrop"

    for artwork_type, names in ARTWORK_RULES.items():
        for name in names:
            if value == name:
                return name

            for separator in (
                "-",
                "_",
                ".",
            ):
                if value.endswith(
                    f"{separator}{name}"
                ):
                    return name

    return None


def _type_for_token(token: str | None):
    if not token:
        return None

    for artwork_type, names in ARTWORK_RULES.items():
        if token in names:
            return artwork_type

    return None


def _priority(artwork: ArtworkFile):
    rules = ARTWORK_RULES.get(
        artwork.artwork_type,
        {},
    )

    return (
        rules.get(
            artwork.source_name,
            999,
        ),
        artwork.relative_path.casefold(),
    )


def serialize_artwork(artwork: ArtworkFile):
    return {
        "id": str(artwork.id),
        "library_id": str(artwork.library_id),
        "target_type": artwork.target_type,
        "target_id": str(artwork.target_id),
        "artwork_type": artwork.artwork_type,
        "artwork_type_label": artwork.get_artwork_type_display(),
        "source_name": artwork.source_name,
        "relative_path": artwork.relative_path,
        "file_name": artwork.file_name,
        "extension": artwork.extension,
        "size_bytes": artwork.size_bytes,
        "is_selected": artwork.is_selected,
        "is_present": artwork.is_present,
        "content_url": f"/api/artwork-files/{artwork.id}/content/",
        "updated_at": artwork.updated_at,
    }


def artwork_for_target(
    *,
    target_type: str,
    target_id,
):
    return [
        serialize_artwork(artwork)
        for artwork in (
            ArtworkFile.objects
            .filter(
                target_type=target_type,
                target_id=target_id,
                is_present=True,
            )
            .order_by(
                "artwork_type",
                "-is_selected",
                "relative_path",
            )
        )
    ]


def _build_location_index(library):
    movie_dirs = defaultdict(list)
    series_dirs = defaultdict(list)
    season_dirs = defaultdict(list)
    episode_stems = defaultdict(list)

    movie_versions = (
        MediaVersion.objects
        .filter(
            media_item__library=library,
            media_item__media_type=(
                MediaItem.MediaType.MOVIE
            ),
            media_file__is_present=True,
        )
        .select_related(
            "media_file",
            "media_item",
        )
    )

    for version in movie_versions:
        path = PurePosixPath(
            version.media_file.relative_path
        )

        movie_dirs[
            path.parent.as_posix()
        ].append(
            version.media_item_id
        )

    episodes = (
        Episode.objects
        .filter(
            media_item__library=library,
            media_item__versions__media_file__is_present=True,
        )
        .select_related(
            "season",
            "season__series",
            "media_item",
        )
        .prefetch_related(
            "media_item__versions__media_file"
        )
        .distinct()
    )

    for episode in episodes:
        for version in episode.media_item.versions.all():
            media_file = version.media_file

            if not media_file.is_present:
                continue

            path = PurePosixPath(
                media_file.relative_path
            )

            parent = path.parent

            episode_stems[
                parent.as_posix()
            ].append(
                (
                    _normalized_stem(path.stem),
                    episode.id,
                )
            )

            season_number = _season_folder_number(
                parent.name
            )

            if (
                season_number is not None
                and season_number
                == episode.season.season_number
            ):
                season_dirs[
                    parent.as_posix()
                ].append(
                    episode.season_id
                )

                series_dirs[
                    parent.parent.as_posix()
                ].append(
                    episode.season.series_id
                )

            else:
                series_dirs[
                    parent.as_posix()
                ].append(
                    episode.season.series_id
                )

    def unique_map(values):
        result = {}

        for path, ids in values.items():
            unique_ids = list(
                dict.fromkeys(ids)
            )

            if len(unique_ids) == 1:
                result[path] = unique_ids[0]

        return result

    return {
        "movie_dirs": unique_map(movie_dirs),
        "series_dirs": unique_map(series_dirs),
        "season_dirs": unique_map(season_dirs),
        "episode_stems": episode_stems,
    }


def _episode_target(
    *,
    parent: str,
    stem: str,
    index,
):
    normalized = _normalized_stem(stem)

    for media_stem, episode_id in index[
        "episode_stems"
    ].get(parent, []):
        candidates = {
            f"{media_stem}-thumb",
            f"{media_stem}_thumb",
            f"{media_stem}.thumb",
        }

        if normalized in candidates:
            return (
                ArtworkFile.TargetType.EPISODE,
                episode_id,
                ArtworkFile.ArtworkType.PRIMARY,
                "thumb",
            )

    return None


def classify_artwork_path(
    *,
    relative_path: str,
    index,
):
    path = PurePosixPath(
        relative_path
    )

    parent = path.parent.as_posix()

    episode = _episode_target(
        parent=parent,
        stem=path.stem,
        index=index,
    )

    if episode:
        return episode

    token = _artwork_token(
        path.stem
    )

    artwork_type = _type_for_token(
        token
    )

    if not artwork_type:
        return None

    if parent in index[
        "season_dirs"
    ]:
        return (
            ArtworkFile.TargetType.SEASON,
            index["season_dirs"][parent],
            artwork_type,
            token,
        )

    if parent in index[
        "movie_dirs"
    ]:
        return (
            ArtworkFile.TargetType.MEDIA_ITEM,
            index["movie_dirs"][parent],
            artwork_type,
            token,
        )

    if parent in index[
        "series_dirs"
    ]:
        return (
            ArtworkFile.TargetType.SERIES,
            index["series_dirs"][parent],
            artwork_type,
            token,
        )

    return None


def discover_artwork_candidates(root: Path):
    candidates = []
    errors = []

    def on_error(error):
        errors.append(error)

    for directory, _directories, filenames in os.walk(
        root,
        onerror=on_error,
    ):
        directory_path = Path(directory)

        for filename in filenames:
            file_path = directory_path / filename

            if file_path.suffix.lower() in IMAGE_EXTENSIONS:
                candidates.append(file_path)

    candidates.sort(
        key=lambda path: str(path).casefold()
    )

    return candidates, errors


def _ensure_selected_artwork(library):
    groups = defaultdict(list)

    for artwork in (
        ArtworkFile.objects
        .filter(
            library=library,
            is_present=True,
        )
    ):
        groups[
            (
                artwork.target_type,
                artwork.target_id,
                artwork.artwork_type,
            )
        ].append(artwork)

    for artworks in groups.values():
        selected = [
            artwork
            for artwork in artworks
            if artwork.is_selected
        ]

        if selected:
            continue

        preferred = min(
            artworks,
            key=_priority,
        )

        preferred.is_selected = True
        preferred.save(
            update_fields=[
                "is_selected",
                "updated_at",
            ]
        )


@transaction.atomic
def sync_artwork_candidates(
    *,
    library,
    root: Path,
    candidates,
    reconcile_missing: bool,
):
    index = _build_location_index(
        library
    )

    scan_time = timezone.now()
    seen_paths = set()
    created = 0
    updated = 0
    ignored = 0
    errors = []

    existing = {
        artwork.relative_path: artwork
        for artwork in (
            ArtworkFile.objects
            .filter(library=library)
        )
    }

    for file_path in candidates:
        try:
            relative_path = (
                file_path
                .relative_to(root)
                .as_posix()
            )

            classification = classify_artwork_path(
                relative_path=relative_path,
                index=index,
            )

            if not classification:
                ignored += 1
                continue

            (
                target_type,
                target_id,
                artwork_type,
                source_name,
            ) = classification

            stat = file_path.stat()
            seen_paths.add(relative_path)

            artwork = existing.get(
                relative_path
            )

            if artwork is None:
                artwork = ArtworkFile.objects.create(
                    library=library,
                    target_type=target_type,
                    target_id=target_id,
                    artwork_type=artwork_type,
                    source_name=source_name,
                    relative_path=relative_path,
                    file_name=file_path.name,
                    extension=(
                        file_path.suffix
                        .lower()
                        .lstrip(".")
                    ),
                    size_bytes=stat.st_size,
                    modified_ns=stat.st_mtime_ns,
                    is_present=True,
                    last_seen_at=scan_time,
                )

                existing[relative_path] = artwork
                created += 1
                continue

            changed = False

            classification_changed = (
                artwork.target_type != target_type
                or artwork.target_id != target_id
                or artwork.artwork_type != artwork_type
            )

            values = {
                "target_type": target_type,
                "target_id": target_id,
                "artwork_type": artwork_type,
                "source_name": source_name,
                "file_name": file_path.name,
                "extension": (
                    file_path.suffix
                    .lower()
                    .lstrip(".")
                ),
                "size_bytes": stat.st_size,
                "modified_ns": stat.st_mtime_ns,
                "is_present": True,
                "last_seen_at": scan_time,
            }

            if classification_changed and artwork.is_selected:
                values["is_selected"] = False

            for field_name, value in values.items():
                if getattr(artwork, field_name) != value:
                    setattr(artwork, field_name, value)
                    changed = True

            if changed:
                artwork.save()
                updated += 1

        except OSError as exc:
            errors.append(
                {
                    "path": str(file_path),
                    "error": str(exc),
                }
            )

    if reconcile_missing:
        missing = (
            ArtworkFile.objects
            .filter(
                library=library,
                is_present=True,
            )
            .exclude(
                relative_path__in=seen_paths
            )
        )

        missing.update(
            is_present=False,
            is_selected=False,
        )

    _ensure_selected_artwork(
        library
    )

    return {
        "created": created,
        "updated": updated,
        "ignored": ignored,
        "error_count": len(errors),
        "errors": errors,
    }


def scan_library_artwork(
    *,
    library,
):
    root = validate_storage_path(
        library.path
    )

    candidates, discovery_errors = (
        discover_artwork_candidates(root)
    )

    result = sync_artwork_candidates(
        library=library,
        root=root,
        candidates=candidates,
        reconcile_missing=(
            not discovery_errors
        ),
    )

    if discovery_errors:
        result["error_count"] += len(
            discovery_errors
        )

        result["errors"].extend(
            {
                "path": str(
                    getattr(
                        error,
                        "filename",
                        root,
                    )
                ),
                "error": str(error),
            }
            for error in discovery_errors
        )

    return result


@transaction.atomic
def select_artwork(
    *,
    artwork: ArtworkFile,
    user,
):
    if not artwork.is_present:
        raise ValueError(
            "Missing artwork cannot be selected."
        )

    previous = (
        ArtworkFile.objects
        .filter(
            library=artwork.library,
            target_type=artwork.target_type,
            target_id=artwork.target_id,
            artwork_type=artwork.artwork_type,
            is_selected=True,
            is_present=True,
        )
        .exclude(pk=artwork.pk)
        .first()
    )

    ArtworkFile.objects.filter(
        library=artwork.library,
        target_type=artwork.target_type,
        target_id=artwork.target_id,
        artwork_type=artwork.artwork_type,
        is_selected=True,
    ).exclude(
        pk=artwork.pk
    ).update(
        is_selected=False
    )

    if not artwork.is_selected:
        artwork.is_selected = True
        artwork.save(
            update_fields=[
                "is_selected",
                "updated_at",
            ]
        )

    old_value = (
        {
            "id": str(previous.id),
            "relative_path": previous.relative_path,
        }
        if previous
        else None
    )

    new_value = {
        "id": str(artwork.id),
        "relative_path": artwork.relative_path,
    }

    if old_value != new_value:
        MetadataChangeSet.objects.create(
            target_type=artwork.target_type,
            target_id=artwork.target_id,
            source=MetadataChangeSet.Source.MANUAL,
            changes={
                f"artwork_{artwork.artwork_type}": {
                    "old": old_value,
                    "new": new_value,
                }
            },
            note=(
                f"Selected preferred {artwork.artwork_type} artwork."
            ),
            changed_by=user,
        )

    return serialize_artwork(
        artwork
    )
