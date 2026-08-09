import os

from datetime import (
    datetime,
    timezone as datetime_timezone,
)

from pathlib import Path

from django.db import (
    IntegrityError,
    transaction,
)

from django.utils import timezone

from catalog.services.resolver import (
    resolve_library_semantics,
)

from jobs.models import ScanJob

from libraries.services.storage import (
    validate_storage_path,
)

from media.constants import VIDEO_EXTENSIONS

from media.models import (
    MediaFile,
    MediaItem,
)

from metadata.models import NfoFile

from metadata.services.nfo import (
    build_media_stem_index,
    sync_nfo_file,
)

from metadata.services.sources import (
    inspect_metadata_sources,
)

from .probe import (
    ProbeError,
    probe_media_file,
)


def _add_error(
    errors,
    path,
    error,
):
    if len(errors) < 100:
        errors.append(
            {
                "path": str(path),
                "error": str(error),
            }
        )


def get_or_create_media_file(
    *,
    library,
    relative_path,
    file_path,
):
    existing = (
        MediaFile.objects
        .filter(
            library=library,
            relative_path=relative_path,
        )
        .select_related(
            "media_item"
        )
        .first()
    )

    if existing:
        return existing, False

    try:
        with transaction.atomic():
            media_item = (
                MediaItem.objects
                .create(
                    library=library,
                    title=file_path.stem,
                )
            )

            media_file = (
                MediaFile.objects
                .create(
                    library=library,
                    media_item=media_item,
                    relative_path=relative_path,
                    file_name=file_path.name,
                    extension=(
                        file_path
                        .suffix
                        .lower()
                        .lstrip(".")
                    ),
                )
            )

        return media_file, True

    except IntegrityError:
        existing = (
            MediaFile.objects
            .filter(
                library=library,
                relative_path=relative_path,
            )
            .select_related(
                "media_item"
            )
            .first()
        )

        if existing is None:
            raise

        return existing, False


def discover_library_files(
    root: Path,
    job: ScanJob,
):
    media_candidates = []
    nfo_candidates = []
    discovery_errors = []

    discovered_total = 0

    def walk_error(
        error,
    ):
        discovery_errors.append(
            error
        )

        _add_error(
            job.errors,
            getattr(
                error,
                "filename",
                root,
            ),
            error,
        )

        job.error_count += 1

    for (
        directory,
        _directories,
        filenames,
    ) in os.walk(
        root,
        onerror=walk_error,
    ):
        directory_path = Path(
            directory
        )

        for filename in filenames:
            file_path = (
                directory_path
                / filename
            )

            extension = (
                file_path
                .suffix
                .lower()
            )

            if (
                extension
                in VIDEO_EXTENSIONS
            ):
                media_candidates.append(
                    file_path
                )

            elif extension == ".nfo":
                nfo_candidates.append(
                    file_path
                )

            else:
                continue

            discovered_total += 1

            if discovered_total % 100 == 0:
                job.total_files = (
                    discovered_total
                )

                job.total_media_files = len(
                    media_candidates
                )

                job.total_nfo_files = len(
                    nfo_candidates
                )

                job.current_path = str(
                    file_path
                )

                job.save(
                    update_fields=[
                        "total_files",
                        "total_media_files",
                        "total_nfo_files",
                        "current_path",
                        "error_count",
                        "errors",
                        "updated_at",
                    ]
                )

    media_candidates.sort(
        key=lambda path:
            str(path).lower()
    )

    nfo_candidates.sort(
        key=lambda path:
            str(path).lower()
    )

    return (
        media_candidates,
        nfo_candidates,
        discovery_errors,
    )


def process_scan_job(
    job: ScanJob,
):
    library = job.library

    root = validate_storage_path(
        library.path
    )

    job.status = ScanJob.Status.DISCOVERING

    job.current_path = (
        "Discovering library files..."
    )

    job.save(
        update_fields=[
            "status",
            "current_path",
            "updated_at",
        ]
    )

    (
        media_candidates,
        nfo_candidates,
        discovery_errors,
    ) = discover_library_files(
        root,
        job,
    )

    job.discovery_had_errors = bool(
        discovery_errors
    )

    job.total_media_files = len(
        media_candidates
    )

    job.total_nfo_files = len(
        nfo_candidates
    )

    job.total_files = (
        job.total_media_files
        + job.total_nfo_files
    )

    job.processed_files = 0
    job.processed_media_files = 0
    job.processed_nfo_files = 0

    job.status = ScanJob.Status.RUNNING

    job.save(
        update_fields=[
            "discovery_had_errors",
            "total_files",
            "total_media_files",
            "total_nfo_files",
            "processed_files",
            "processed_media_files",
            "processed_nfo_files",
            "status",
            "error_count",
            "errors",
            "updated_at",
        ]
    )

    existing_files = {
        media_file.relative_path:
            media_file

        for media_file
        in MediaFile.objects
        .filter(
            library=library
        )
        .select_related(
            "media_item"
        )
    }

    seen_media_paths = set()
    seen_nfo_paths = set()

    scan_time = timezone.now()

    created = 0
    updated = 0
    skipped = 0

    nfo_created = 0
    nfo_updated = 0

    for index, file_path in enumerate(
        media_candidates,
        start=1,
    ):
        relative_path = None

        try:
            stat = file_path.stat()

            relative_path = (
                file_path
                .relative_to(root)
                .as_posix()
            )

            seen_media_paths.add(
                relative_path
            )

            media_file = (
                existing_files.get(
                    relative_path
                )
            )

            unchanged = (
                media_file is not None

                and media_file.size_bytes
                == stat.st_size

                and media_file.modified_ns
                == stat.st_mtime_ns

                and media_file.probe_status
                == MediaFile.ProbeStatus.OK
            )

            if unchanged:
                media_file.is_present = True
                media_file.last_seen_at = scan_time

                media_file.save(
                    update_fields=[
                        "is_present",
                        "last_seen_at",
                        "updated_at",
                    ]
                )

                inspect_metadata_sources(
                    file_path=file_path,
                    media_file=media_file,
                    probe_raw=(
                        media_file.raw_probe
                    ),
                    probe_error=(
                        media_file.probe_error
                    ),
                )

                skipped += 1

            else:
                if media_file is None:
                    (
                        media_file,
                        is_new,
                    ) = get_or_create_media_file(
                        library=library,
                        relative_path=relative_path,
                        file_path=file_path,
                    )

                    existing_files[
                        relative_path
                    ] = media_file

                else:
                    is_new = False

                media_file.file_name = (
                    file_path.name
                )

                media_file.extension = (
                    file_path
                    .suffix
                    .lower()
                    .lstrip(".")
                )

                media_file.size_bytes = (
                    stat.st_size
                )

                media_file.modified_ns = (
                    stat.st_mtime_ns
                )

                media_file.source_modified_at = (
                    datetime.fromtimestamp(
                        stat.st_mtime,
                        tz=(
                            datetime_timezone.utc
                        ),
                    )
                )

                media_file.last_seen_at = scan_time
                media_file.is_present = True

                probe_raw = None
                probe_error = ""

                try:
                    probe = probe_media_file(
                        file_path
                    )

                    probe_raw = probe["raw"]

                    media_file.duration_seconds = (
                        probe[
                            "duration_seconds"
                        ]
                    )

                    media_file.container_format = (
                        probe[
                            "container_format"
                        ]
                    )

                    media_file.bit_rate = (
                        probe[
                            "bit_rate"
                        ]
                    )

                    media_file.video_codec = (
                        probe[
                            "video_codec"
                        ]
                    )

                    media_file.width = (
                        probe["width"]
                    )

                    media_file.height = (
                        probe["height"]
                    )

                    media_file.frame_rate = (
                        probe[
                            "frame_rate"
                        ]
                    )

                    media_file.audio_codec = (
                        probe[
                            "audio_codec"
                        ]
                    )

                    media_file.audio_channels = (
                        probe[
                            "audio_channels"
                        ]
                    )

                    media_file.raw_probe = (
                        probe_raw
                    )

                    media_file.probe_status = (
                        MediaFile
                        .ProbeStatus
                        .OK
                    )

                    media_file.probe_error = ""

                except ProbeError as exc:
                    probe_error = str(
                        exc
                    )

                    media_file.probe_status = (
                        MediaFile
                        .ProbeStatus
                        .ERROR
                    )

                    media_file.probe_error = (
                        probe_error
                    )

                    _add_error(
                        job.errors,
                        relative_path,
                        probe_error,
                    )

                    job.error_count += 1

                media_file.save()

                inspect_metadata_sources(
                    file_path=file_path,
                    media_file=media_file,
                    probe_raw=probe_raw,
                    probe_error=probe_error,
                )

                if is_new:
                    created += 1
                else:
                    updated += 1

        except OSError as exc:
            _add_error(
                job.errors,
                relative_path
                or file_path,
                exc,
            )

            job.error_count += 1

        finally:
            job.processed_media_files = index

            job.processed_files = (
                job.processed_media_files
                + job.processed_nfo_files
            )

            job.current_path = (
                relative_path
                or str(file_path)
            )

            job.created_count = created
            job.updated_count = updated
            job.skipped_count = skipped

            if (
                index % 5 == 0
                or index
                == len(media_candidates)
            ):
                job.save(
                    update_fields=[
                        "processed_files",
                        "processed_media_files",
                        "current_path",
                        "created_count",
                        "updated_count",
                        "skipped_count",
                        "error_count",
                        "errors",
                        "updated_at",
                    ]
                )

    all_media_files = list(
        MediaFile.objects
        .filter(
            library=library
        )
        .select_related(
            "media_item"
        )
    )

    (
        media_stem_index,
        folder_index,
    ) = build_media_stem_index(
        all_media_files
    )

    for index, nfo_path in enumerate(
        nfo_candidates,
        start=1,
    ):
        relative_path = None

        try:
            relative_path = (
                nfo_path
                .relative_to(root)
                .as_posix()
            )

            seen_nfo_paths.add(
                relative_path
            )

            (
                _nfo,
                created_nfo,
                updated_nfo,
            ) = sync_nfo_file(
                library=library,
                root=root,
                nfo_path=nfo_path,
                media_stem_index=(
                    media_stem_index
                ),
                folder_index=(
                    folder_index
                ),
                scan_time=scan_time,
            )

            if created_nfo:
                nfo_created += 1

            elif updated_nfo:
                nfo_updated += 1

        except OSError as exc:
            _add_error(
                job.errors,
                relative_path
                or nfo_path,
                exc,
            )

            job.error_count += 1

        finally:
            job.processed_nfo_files = index

            job.processed_files = (
                job.processed_media_files
                + job.processed_nfo_files
            )

            job.current_path = (
                relative_path
                or str(nfo_path)
            )

            job.nfo_created_count = (
                nfo_created
            )

            job.nfo_updated_count = (
                nfo_updated
            )

            if (
                index % 5 == 0
                or index
                == len(nfo_candidates)
            ):
                job.save(
                    update_fields=[
                        "processed_files",
                        "processed_nfo_files",
                        "current_path",
                        "nfo_created_count",
                        "nfo_updated_count",
                        "error_count",
                        "errors",
                        "updated_at",
                    ]
                )

    if not job.discovery_had_errors:
        MediaFile.objects.filter(
            library=library,
        ).exclude(
            relative_path__in=(
                seen_media_paths
            )
        ).update(
            is_present=False,
        )

        NfoFile.objects.filter(
            library=library,
        ).exclude(
            relative_path__in=(
                seen_nfo_paths
            )
        ).update(
            is_present=False,
        )

    job.current_path = (
        "Building semantic catalog..."
    )

    job.save(
        update_fields=[
            "current_path",
            "updated_at",
        ]
    )

    semantic_result = (
        resolve_library_semantics(
            library=library
        )
    )

    if semantic_result[
        "error_count"
    ]:
        for semantic_error in (
            semantic_result[
                "errors"
            ]
        ):
            _add_error(
                job.errors,
                semantic_error[
                    "path"
                ],
                semantic_error[
                    "error"
                ],
            )

        job.error_count += (
            semantic_result[
                "error_count"
            ]
        )

        job.save(
            update_fields=[
                "error_count",
                "errors",
                "updated_at",
            ]
        )

    library.last_scanned_at = timezone.now()

    library.save(
        update_fields=[
            "last_scanned_at",
            "updated_at",
        ]
    )

    job.current_path = ""
    job.completed_at = timezone.now()

    if job.error_count:
        job.status = (
            ScanJob.Status
            .COMPLETED_WITH_ERRORS
        )
    else:
        job.status = (
            ScanJob.Status.COMPLETED
        )

    job.save()
