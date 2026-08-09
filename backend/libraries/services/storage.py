import os
import uuid
from pathlib import Path

from media.constants import VIDEO_EXTENSIONS


class StorageAccessError(Exception):
    pass


def validate_storage_path(
    raw_path: str,
) -> Path:
    raw_path = raw_path.strip()

    if not raw_path:
        raise StorageAccessError(
            "A library path is required."
        )

    path = Path(
        raw_path
    ).expanduser()

    try:
        if not path.exists():
            raise StorageAccessError(
                "This path does not exist "
                "on the LibraryForge server."
            )

        if not path.is_dir():
            raise StorageAccessError(
                "This path is not a directory."
            )

        # Actually try to enumerate it.
        # os.access() alone is not reliable enough
        # for network shares.
        with os.scandir(path) as entries:
            next(entries, None)

    except StorageAccessError:
        raise

    except PermissionError as exc:
        raise StorageAccessError(
            "LibraryForge does not have permission "
            "to access this path."
        ) from exc

    except OSError as exc:
        if getattr(
            exc,
            "winerror",
            None,
        ) == 1326:
            raise StorageAccessError(
                "Windows could not authenticate to "
                "this network share."
            ) from exc

        raise StorageAccessError(
            f"LibraryForge could not access "
            f"this path: {exc}"
        ) from exc

    return path


def _result(
    status: str,
    detail: str,
):
    return {
        "status": status,
        "detail": detail,
    }


def _find_sample_media(
    root: Path,
):
    directories_checked = 0

    walk_errors: list[OSError] = []

    def on_error(
        error: OSError,
    ):
        walk_errors.append(
            error
        )

    for (
        directory,
        _directories,
        filenames,
    ) in os.walk(
        root,
        onerror=on_error,
    ):
        directories_checked += 1

        directory_path = Path(
            directory
        )

        for filename in filenames:
            candidate = (
                directory_path
                / filename
            )

            if (
                candidate
                .suffix
                .lower()
                not in VIDEO_EXTENSIONS
            ):
                continue

            try:
                candidate.stat()

                return (
                    candidate,
                    walk_errors,
                )

            except OSError as exc:
                return (
                    None,
                    walk_errors
                    + [exc],
                )

        # A storage test should not become
        # an accidental full library scan.
        if directories_checked >= 25:
            break

    return (
        None,
        walk_errors,
    )


def test_storage_capabilities(
    raw_path: str,
):
    capabilities = {
        "path_exists": _result(
            "not_tested",
            "Not tested.",
        ),

        "directory": _result(
            "not_tested",
            "Not tested.",
        ),

        "read_access": _result(
            "not_tested",
            "Not tested.",
        ),

        "media_access": _result(
            "not_tested",
            "Not tested.",
        ),

        "write_access": _result(
            "not_tested",
            "Not tested.",
        ),

        "sidecar_creation": _result(
            "not_tested",
            "Not tested.",
        ),

        "rename": _result(
            "not_tested",
            "Not tested.",
        ),

        "hardlink": _result(
            "not_tested",
            "Not tested.",
        ),

        "symlink": _result(
            "not_tested",
            "Not tested.",
        ),
    }

    raw_path = raw_path.strip()

    if not raw_path:
        return {
            "path": raw_path,
            "accessible": False,
            "capabilities": capabilities,
            "recommended_management_mode": None,
        }

    path = Path(
        raw_path
    ).expanduser()

    try:
        exists = path.exists()

        if not exists:
            capabilities[
                "path_exists"
            ] = _result(
                "failed",
                "Path does not exist.",
            )

            return {
                "path": str(path),
                "accessible": False,
                "capabilities": capabilities,
                "recommended_management_mode": None,
            }

        capabilities[
            "path_exists"
        ] = _result(
            "passed",
            "Path exists.",
        )

    except OSError as exc:
        capabilities[
            "path_exists"
        ] = _result(
            "failed",
            str(exc),
        )

        return {
            "path": str(path),
            "accessible": False,
            "capabilities": capabilities,
            "recommended_management_mode": None,
        }

    try:
        if not path.is_dir():
            capabilities[
                "directory"
            ] = _result(
                "failed",
                "Path is not a directory.",
            )

            return {
                "path": str(path),
                "accessible": False,
                "capabilities": capabilities,
                "recommended_management_mode": None,
            }

        capabilities[
            "directory"
        ] = _result(
            "passed",
            "Path is a directory.",
        )

    except OSError as exc:
        capabilities[
            "directory"
        ] = _result(
            "failed",
            str(exc),
        )

        return {
            "path": str(path),
            "accessible": False,
            "capabilities": capabilities,
            "recommended_management_mode": None,
        }

    try:
        with os.scandir(path) as entries:
            next(
                entries,
                None,
            )

        capabilities[
            "read_access"
        ] = _result(
            "passed",
            "Directory can be read.",
        )

    except OSError as exc:
        capabilities[
            "read_access"
        ] = _result(
            "failed",
            str(exc),
        )

        return {
            "path": str(path),
            "accessible": False,
            "capabilities": capabilities,
            "recommended_management_mode": None,
        }

    sample_media, media_errors = (
        _find_sample_media(
            path
        )
    )

    if sample_media:
        capabilities[
            "media_access"
        ] = _result(
            "passed",
            (
                "Media file accessible: "
                f"{sample_media.name}"
            ),
        )

    elif media_errors:
        capabilities[
            "media_access"
        ] = _result(
            "failed",
            str(
                media_errors[0]
            ),
        )

    else:
        capabilities[
            "media_access"
        ] = _result(
            "not_tested",
            (
                "No supported media file "
                "was found in the sample."
            ),
        )

    token = uuid.uuid4().hex

    source_file = (
        path
        / (
            ".libraryforge-"
            f"{token}.tmp"
        )
    )

    renamed_file = (
        path
        / (
            ".libraryforge-"
            f"{token}-renamed.tmp"
        )
    )

    sidecar_file = (
        path
        / (
            ".libraryforge-"
            f"{token}.nfo"
        )
    )

    hardlink_file = (
        path
        / (
            ".libraryforge-"
            f"{token}-hardlink.tmp"
        )
    )

    symlink_file = (
        path
        / (
            ".libraryforge-"
            f"{token}-symlink.tmp"
        )
    )

    cleanup_paths = [
        symlink_file,
        hardlink_file,
        sidecar_file,
        renamed_file,
        source_file,
    ]

    try:
        try:
            source_file.touch(
                exist_ok=False
            )

            capabilities[
                "write_access"
            ] = _result(
                "passed",
                (
                    "Temporary file "
                    "creation succeeded."
                ),
            )

        except OSError as exc:
            capabilities[
                "write_access"
            ] = _result(
                "failed",
                str(exc),
            )

            return {
                "path": str(path),
                "accessible": True,
                "capabilities": capabilities,
                "recommended_management_mode": "read_only",
            }

        try:
            sidecar_file.touch(
                exist_ok=False
            )

            capabilities[
                "sidecar_creation"
            ] = _result(
                "passed",
                (
                    "Temporary .nfo "
                    "creation succeeded."
                ),
            )

        except OSError as exc:
            capabilities[
                "sidecar_creation"
            ] = _result(
                "failed",
                str(exc),
            )

        try:
            source_file.rename(
                renamed_file
            )

            renamed_file.rename(
                source_file
            )

            capabilities[
                "rename"
            ] = _result(
                "passed",
                "Rename succeeded.",
            )

        except OSError as exc:
            capabilities[
                "rename"
            ] = _result(
                "failed",
                str(exc),
            )

        try:
            os.link(
                source_file,
                hardlink_file,
            )

            capabilities[
                "hardlink"
            ] = _result(
                "passed",
                "Hardlink creation succeeded.",
            )

        except OSError as exc:
            capabilities[
                "hardlink"
            ] = _result(
                "failed",
                str(exc),
            )

        try:
            os.symlink(
                source_file,
                symlink_file,
            )

            capabilities[
                "symlink"
            ] = _result(
                "passed",
                "Symbolic link creation succeeded.",
            )

        except OSError as exc:
            capabilities[
                "symlink"
            ] = _result(
                "failed",
                str(exc),
            )

    finally:
        for cleanup_path in cleanup_paths:
            try:
                cleanup_path.unlink(
                    missing_ok=True
                )
            except OSError:
                pass

    write_ok = (
        capabilities[
            "write_access"
        ]["status"]
        == "passed"
    )

    sidecar_ok = (
        capabilities[
            "sidecar_creation"
        ]["status"]
        == "passed"
    )

    rename_ok = (
        capabilities[
            "rename"
        ]["status"]
        == "passed"
    )

    if (
        write_ok
        and sidecar_ok
        and rename_ok
    ):
        recommended_mode = (
            "full_control"
        )

    elif (
        write_ok
        and sidecar_ok
    ):
        recommended_mode = (
            "sidecar_only"
        )

    else:
        recommended_mode = (
            "read_only"
        )

    return {
        "path": str(path),
        "accessible": True,
        "capabilities": capabilities,
        "recommended_management_mode":
            recommended_mode,
    }