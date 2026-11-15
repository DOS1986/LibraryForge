"""Choose provider artwork for a movie or series and save it beside the item.

Artwork is offered by the provider a title was matched with (TMDB or
TheTVDB details) or by an artwork provider that looks titles up by ID
(Fanart.tv). Listing never writes anything. Saving one image:

1. Recomputes what the provider offers and refuses a URL it doesn't offer, so
   a request can't make LibraryForge fetch arbitrary addresses.
2. Downloads it through the hardened remote-artwork fetcher (HTTPS, the
   provider's own image host, bounded size, no unchecked redirects) and
   checks it really is a JPEG, PNG, or WebP image of sensible dimensions.
3. Writes it into the item's own folder under the name Jellyfin and
   LibraryForge's scanner both read: ``poster``, ``fanart``, ``logo``,
   ``banner``, or ``landscape``, with the image's real extension.
4. Keeps whatever it replaces. Existing images of that type in the folder
   that LibraryForge didn't write are only replaced when the person confirms,
   and are renamed to ``<name>.libraryforge-backup-<time>.<ext>``, which
   neither Jellyfin nor the scanner treats as artwork. A file LibraryForge
   saved earlier is replaced without a backup if it's unchanged.
5. Records the new file in the artwork catalog, selects it, and writes
   provider provenance and a history entry, in one transaction. If anything
   fails, the folder is put back the way it was.

Movies must be in a folder of their own (a poster.jpg in a shared folder would
apply to every movie in it), and read-only libraries are never written.
"""

from __future__ import annotations

import hashlib
import os
import re
import struct
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

from django.db import transaction
from django.utils import timezone

from catalog.models import (
    ArtworkFile,
    CanonicalFieldState,
    MediaVersion,
    MetadataChangeSet,
)
from catalog.services.artwork import (
    IMAGE_EXTENSIONS,
    _artwork_token,
    _build_location_index,
    _type_for_token,
    classify_artwork_path,
    serialize_artwork,
)
from integrations.providers.base import provider_supports_metadata_target
from integrations.registry import get_provider_class
from integrations.security import (
    PROVIDER_IMAGE_HOSTS,
    artwork_url_downloadable,
    fetch_remote_artwork,
)
from integrations.services import active_links_for_library, provider_for_connection
from libraries.models import Library
from metadata.providers.types import (
    ArtworkKind,
    MetadataErrorCategory,
    MetadataProviderError,
    MetadataTargetType,
)
from metadata.services import secure_nfo
from metadata.services.provider_apply import ApplyConflict
from metadata.services.provider_match import MatchRequestError, ResolvedTarget

MAX_IMAGE_BYTES = 25 * 1024 * 1024
MIN_DIMENSION = 16
MAX_DIMENSION = 12_000

# Provider artwork kind -> LibraryForge artwork type and the file name written.
KIND_TYPES = {
    ArtworkKind.POSTER: ("primary", "poster"),
    ArtworkKind.BACKDROP: ("backdrop", "fanart"),
    ArtworkKind.LOGO: ("logo", "logo"),
    ArtworkKind.BANNER: ("banner", "banner"),
    ArtworkKind.THUMBNAIL: ("thumb", "landscape"),
}
TYPE_ORDER = ("primary", "backdrop", "logo", "banner", "thumb")

MODE_DETAILS = "details"  # artwork comes with the matched title's details
MODE_IDS = "ids"  # artwork is looked up by external IDs

# Season images that live in a series folder (season01-poster.jpg) belong to
# seasons, so they're never treated as the series' own artwork.
_SEASON_IMAGE = re.compile(r"^season[ ._-]*(\d+|specials|all)\b", re.IGNORECASE)
_BACKUP_MARK = ".libraryforge-backup-"
_ID_VALUE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


# ---------------------------------------------------------------------------
# Sources and what they offer
# ---------------------------------------------------------------------------


def _sources(resolved: ResolvedTarget) -> list[tuple[dict[str, Any], Any]]:
    rows: list[tuple[dict[str, Any], Any]] = []
    seen: set[str] = set()
    for link in active_links_for_library(library=resolved.library):
        capabilities = set(link.capabilities or [])
        if str(link.connection_id) in seen or not capabilities & {"metadata", "artwork"}:
            continue
        try:
            provider_class = get_provider_class(link.connection.provider)
        except ValueError:
            continue
        definition = provider_class.definition
        namespaces = (getattr(provider_class, "artwork_id_namespaces", {}) or {}).get(resolved.kind.value)
        if namespaces and "artwork" in capabilities:
            mode = MODE_IDS
        elif "metadata" in capabilities and provider_supports_metadata_target(definition, resolved.kind):
            mode = MODE_DETAILS
        else:
            continue
        if definition.key not in PROVIDER_IMAGE_HOSTS:
            # The provider's terms don't allow saving its images (OMDb).
            continue
        seen.add(str(link.connection_id))
        rows.append(
            (
                {
                    "connection_id": str(link.connection_id),
                    "connection_name": link.connection.name,
                    "provider": definition.key,
                    "provider_label": definition.label,
                    "mode": mode,
                    "id_namespaces": list(namespaces or ()),
                    "attribution": definition.attribution,
                },
                link,
            )
        )
    return rows


def _source(resolved: ResolvedTarget, connection_id: str | None):
    rows = _sources(resolved)
    if connection_id:
        rows = [(row, link) for row, link in rows if row["connection_id"] == str(connection_id)]
    if not rows:
        raise MatchRequestError("Choose an artwork source assigned to this library that allows saving its images.")
    row, link = rows[0]
    return row, link, provider_for_connection(link.connection)


def _clean_ids(values: Any) -> dict[str, str]:
    if not isinstance(values, dict):
        return {}
    output = {}
    for key, value in list(values.items())[:10]:
        name, text = str(key).strip().casefold(), str(value or "").strip()
        if name in ("tmdb", "imdb", "tvdb") and _ID_VALUE.fullmatch(text):
            output[name] = text
    return output


def _offered(resolved: ResolvedTarget, row, provider, *, source_id: str | None, ids: dict[str, str]):
    if row["mode"] == MODE_DETAILS:
        if not source_id:
            raise MatchRequestError("Choose a match first: its provider supplies the artwork.")
        detail = provider.get_metadata(target_type=resolved.kind, source_id=source_id)
        artwork = list(detail.artwork)
    else:
        known = {str(key).casefold(): str(value) for key, value in (resolved.current.get("external_ids") or {}).items()}
        merged = {**known, **ids}
        artwork = provider.find_artwork(target_type=resolved.kind.value, external_ids=merged)
    return [item for item in artwork if item.kind in KIND_TYPES and artwork_url_downloadable(item.url, row["provider"])]


# ---------------------------------------------------------------------------
# Where the files go
# ---------------------------------------------------------------------------


def _folder(resolved: ResolvedTarget, index) -> str:
    obj = resolved.obj
    if resolved.kind == MetadataTargetType.MOVIE:
        parents = {
            PurePosixPath(version.media_file.relative_path).parent.as_posix()
            for version in MediaVersion.objects.filter(media_item=obj, media_file__is_present=True).select_related(
                "media_file"
            )
        }
        if not parents:
            raise MatchRequestError("This movie has no file in the library right now, so there's no folder for artwork.")
        own = [parent for parent in parents if index["movie_dirs"].get(parent) == obj.id]
        if not own:
            raise MatchRequestError(
                "This movie shares its folder with other movies, so artwork saved there would apply to all of "
                "them. Give it a folder of its own to save artwork."
            )
    else:
        own = [folder for folder, series_id in index["series_dirs"].items() if series_id == obj.id]
        if not own:
            raise MatchRequestError("LibraryForge couldn't find this series' own folder. Rescan the library first.")
    if len(own) > 1:
        raise MatchRequestError("This item's files are in several folders, so it's unclear where its artwork belongs.")
    return own[0]


def _library_root(library: Library) -> Path:
    return Path(library.path).expanduser().resolve(strict=True)


def _directory(root: Path, folder: str) -> Path:
    parts = PurePosixPath(folder).parts if folder not in ("", ".") else ()
    if ".." in parts:
        raise MatchRequestError("The item's folder path is invalid.")
    directory = root.joinpath(*parts).resolve(strict=True)
    if not (directory == root or directory.is_relative_to(root)) or not directory.is_dir():
        raise MatchRequestError("The item's folder isn't inside the library.")
    return directory


def _relative(folder: str, name: str) -> str:
    return name if folder in ("", ".") else f"{folder}/{name}"


def _existing(directory: Path, folder: str, artwork_type: str, kind: MetadataTargetType) -> list[str]:
    """Images in the folder that Jellyfin or the scanner would read as this type."""

    found = []
    with os.scandir(directory) as entries:
        for entry in entries:
            path = Path(entry.path)
            if not entry.is_file(follow_symlinks=False) or path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            if _BACKUP_MARK in path.stem or (kind == MetadataTargetType.SERIES and _SEASON_IMAGE.match(path.stem)):
                continue
            if _type_for_token(_artwork_token(path.stem)) == artwork_type:
                found.append(_relative(folder, entry.name))
    return sorted(found, key=str.casefold)


def _state(resolved: ResolvedTarget, artwork_type: str) -> CanonicalFieldState | None:
    return CanonicalFieldState.objects.filter(
        target_type=resolved.field_state_type, target_id=resolved.obj.id, field_name=f"artwork_{artwork_type}"
    ).first()


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_ours(path: Path, relative: str, state: CanonicalFieldState | None) -> bool:
    if state is None:
        return False
    snapshot = state.value_snapshot or {}
    return (
        isinstance(snapshot, dict)
        and state.source == CanonicalFieldState.Source.PROVIDER
        and snapshot.get("path") == relative
        and bool(snapshot.get("sha256"))
        and _file_sha(path) == snapshot["sha256"]
    )


# ---------------------------------------------------------------------------
# Image checks
# ---------------------------------------------------------------------------


def sniff_image(data: bytes) -> tuple[str, int, int] | None:
    """(extension, width, height) for a JPEG, PNG, or WebP image, else None."""

    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24 and data[12:16] == b"IHDR":
        width, height = struct.unpack(">II", data[16:24])
        return "png", width, height
    if data.startswith(b"\xff\xd8"):
        offset = 2
        while offset + 9 < len(data):
            if data[offset] != 0xFF:
                return None
            marker = data[offset + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                offset += 2
                continue
            (length,) = struct.unpack(">H", data[offset + 2 : offset + 4])
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                height, width = struct.unpack(">HH", data[offset + 5 : offset + 9])
                return "jpg", width, height
            if length < 2:
                return None
            offset += 2 + length
        return None
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) >= 30:
        chunk = data[12:16]
        if chunk == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
            width, height = struct.unpack("<HH", data[26:30])
            return "webp", width & 0x3FFF, height & 0x3FFF
        if chunk == b"VP8L" and data[20] == 0x2F:
            bits = int.from_bytes(data[21:25], "little")
            return "webp", (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if chunk == b"VP8X":
            width = int.from_bytes(data[24:27], "little") + 1
            height = int.from_bytes(data[27:30], "little") + 1
            return "webp", width, height
    return None


def _download(item, row, provider) -> tuple[bytes, str, int, int]:
    remote = fetch_remote_artwork(
        artwork_url=item.url,
        provider=provider,
        connection_provider=row["provider"],
        max_bytes=MAX_IMAGE_BYTES,
    )
    if remote is None or not remote.body:
        raise MetadataProviderError(
            MetadataErrorCategory.UNAVAILABLE, f"{row['provider_label']} didn't return that image. Try again or pick another."
        )
    if len(remote.body) > MAX_IMAGE_BYTES:
        raise MatchRequestError("That image is too large to save.")
    sniffed = sniff_image(remote.body)
    if sniffed is None:
        raise MatchRequestError("That download isn't a JPEG, PNG, or WebP image, so it wasn't saved.")
    extension, width, height = sniffed
    if not (MIN_DIMENSION <= width <= MAX_DIMENSION and MIN_DIMENSION <= height <= MAX_DIMENSION):
        raise MatchRequestError("That image has unusual dimensions, so it wasn't saved.")
    return remote.body, extension, width, height


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def _writability(library: Library) -> tuple[bool, str | None]:
    writable = library.management_mode != Library.ManagementMode.READ_ONLY
    return writable, secure_nfo.library_root_error(library) if writable else None


def _current(resolved: ResolvedTarget) -> dict[str, Any]:
    output: dict[str, Any] = dict.fromkeys(TYPE_ORDER)
    for artwork in ArtworkFile.objects.filter(
        library=resolved.library,
        target_type=resolved.field_state_type,
        target_id=resolved.obj.id,
        is_selected=True,
        is_present=True,
    ):
        if artwork.artwork_type in output:
            output[artwork.artwork_type] = serialize_artwork(artwork)
    return output


def artwork_choices(
    resolved: ResolvedTarget,
    *,
    connection_id: str | None,
    source_id: str | None = None,
    ids: Any = None,
    prefer_id: str | None = None,
) -> dict[str, Any]:
    """What a source offers. Without ``connection_id``, uses ``prefer_id`` (the
    connection the title was matched with) if it's a source, else the first
    source that looks titles up by ID; details sources need their own match."""

    sources = [row for row, _link in _sources(resolved)]
    if not connection_id:
        preferred = [row for row in sources if prefer_id and row["connection_id"] == str(prefer_id)]
        by_ids = [row for row in sources if row["mode"] == MODE_IDS]
        chosen = (preferred or by_ids or [None])[0]
        connection_id = chosen["connection_id"] if chosen else None
    writable, root_error = _writability(resolved.library)
    base = {
        "target": resolved.summary(),
        "sources": sources,
        "writable": writable,
        "root_error": root_error,
        "current": _current(resolved),
    }
    if not connection_id:
        return {**base, "connection": None, "items": [], "folder": None, "folder_error": None}

    row, _link, provider = _source(resolved, connection_id)
    items = _offered(resolved, row, provider, source_id=source_id, ids=_clean_ids(ids))
    folder, folder_error = None, None
    try:
        folder = _folder(resolved, _build_location_index(resolved.library))
    except MatchRequestError as error:
        folder_error = error.message
    return {
        **base,
        "connection": row,
        "folder": folder,
        "folder_error": folder_error,
        "items": [
            {
                **item.to_dict(),
                "artwork_type": KIND_TYPES[item.kind][0],
                "file_name": KIND_TYPES[item.kind][1],
            }
            for item in items
        ],
    }


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------


def _replay(resolved: ResolvedTarget, operation_id) -> dict[str, Any] | None:
    existing = MetadataChangeSet.objects.filter(operation_id=operation_id).first()
    if existing is None:
        return None
    if existing.target_id != resolved.obj.id or not (existing.details or {}).get("artwork"):
        raise ApplyConflict("This operation ID was already used for a different change.", code="operation_reused")
    details = existing.details or {}
    artwork = ArtworkFile.objects.filter(library=resolved.library, relative_path=details.get("path")).first()
    return {
        "replayed": True,
        "artwork_type": details.get("artwork_type"),
        "path": details.get("path"),
        "backups": details.get("backups") or [],
        "artwork": serialize_artwork(artwork) if artwork else None,
        "change_set_id": str(existing.id),
    }


def _backup_name(directory: Path, name: str, stamp: str) -> str:
    stem, suffix = Path(name).stem, Path(name).suffix
    candidate = f"{stem}{_BACKUP_MARK}{stamp}{suffix}"
    counter = 2
    while (directory / candidate).exists():
        candidate = f"{stem}{_BACKUP_MARK}{stamp}-{counter}{suffix}"
        counter += 1
    return candidate


def save_artwork(*, user, resolved: ResolvedTarget, request: dict[str, Any]) -> dict[str, Any]:
    replay = _replay(resolved, request["operation_id"])
    if replay is not None:
        return replay

    library = resolved.library
    writable, root_error = _writability(library)
    if not writable:
        raise MatchRequestError(
            "This library is Read Only, so LibraryForge can't save artwork into it. Change its management mode "
            "to Sidecar Only to allow it.",
            status=409,
        )
    if root_error:
        raise MatchRequestError(root_error, status=409)

    row, _link, provider = _source(resolved, request.get("connection"))
    offered = _offered(resolved, row, provider, source_id=request.get("source_id"), ids=_clean_ids(request.get("ids")))
    item = next((value for value in offered if value.url == request["url"]), None)
    if item is None:
        raise ApplyConflict(
            f"{row['provider_label']} doesn't offer that image for this title anymore. Load the artwork again.",
            code="not_offered",
        )
    artwork_type, base_name = KIND_TYPES[item.kind]

    index = _build_location_index(library)
    folder = _folder(resolved, index)
    root = _library_root(library)
    directory = _directory(root, folder)
    state = _state(resolved, artwork_type)

    existing = _existing(directory, folder, artwork_type, resolved.kind)
    foreign = [path for path in existing if not _is_ours(root.joinpath(*PurePosixPath(path).parts), path, state)]
    if foreign and not request.get("replace"):
        raise ApplyConflict(
            "This item already has "
            + ("artwork" if len(foreign) > 1 else "an image")
            + f" of that type: {', '.join(PurePosixPath(path).name for path in foreign)}. Confirm to replace it; "
            "the current file is kept as a backup.",
            code="existing_artwork",
        )

    data, extension, width, height = _download(item, row, provider)
    sha = hashlib.sha256(data).hexdigest()
    name = f"{base_name}.{extension}"
    relative = _relative(folder, name)
    classified = classify_artwork_path(relative_path=relative, index=index)
    if not classified or (classified[0], classified[1], classified[2]) != (
        resolved.field_state_type,
        resolved.obj.id,
        artwork_type,
    ):
        raise MatchRequestError("LibraryForge couldn't place this artwork so its library scan would keep it.")

    stamp = timezone.now().strftime("%Y%m%d%H%M%S")
    moved: list[tuple[Path, Path]] = []  # (original, moved-to)
    backups: list[dict[str, str]] = []
    discard: list[Path] = []
    target = directory / name
    temporary = directory / f".libraryforge-{uuid.uuid4().hex}.tmp"
    wrote = False
    try:
        for path in existing:
            original = root.joinpath(*PurePosixPath(path).parts)
            if path in foreign:
                backup = directory / _backup_name(directory, original.name, stamp)
                os.replace(original, backup)
                backups.append({"from": path, "to": _relative(folder, backup.name)})
            else:
                # Our own earlier save: set aside, deleted once this one is recorded.
                backup = directory / f".libraryforge-old-{uuid.uuid4().hex}{original.suffix}"
                os.replace(original, backup)
                discard.append(backup)
            moved.append((original, backup))
        if target.exists() or target.is_symlink():
            raise MatchRequestError("Another file is in the way of the new artwork.", status=409)
        with temporary.open("xb") as handle:
            handle.write(data)
        os.replace(temporary, target)
        wrote = True
        stat = target.stat()
        change_set = _record(
            user=user,
            resolved=resolved,
            request=request,
            row=row,
            item=item,
            artwork_type=artwork_type,
            relative=relative,
            replaced=existing,
            backups=backups,
            sha=sha,
            size=stat.st_size,
            modified_ns=stat.st_mtime_ns,
            width=width,
            height=height,
        )
    except BaseException:
        # Put the folder back the way it was.
        if temporary.exists():
            temporary.unlink()
        if wrote and target.exists():
            target.unlink()
        for original, backup in reversed(moved):
            if backup.exists() and not original.exists():
                os.replace(backup, original)
        raise

    for path in discard:
        try:
            path.unlink()
        except OSError:
            pass
    artwork = ArtworkFile.objects.get(library=library, relative_path=relative)
    return {
        "replayed": False,
        "artwork_type": artwork_type,
        "path": relative,
        "backups": backups,
        "artwork": serialize_artwork(artwork),
        "change_set_id": str(change_set.id),
    }


def _record(
    *,
    user,
    resolved: ResolvedTarget,
    request,
    row,
    item,
    artwork_type,
    relative,
    replaced,
    backups,
    sha,
    size,
    modified_ns,
    width,
    height,
) -> MetadataChangeSet:
    library = resolved.library
    target = {"library": library, "target_type": resolved.field_state_type, "target_id": resolved.obj.id}
    source_ref = (
        f"{row['provider']}:{resolved.kind.value}:{request.get('source_id') or ','.join(sorted(_clean_ids(request.get('ids')).values()))}"
    )[:255]
    with transaction.atomic():
        previous = ArtworkFile.objects.filter(**target, artwork_type=artwork_type, is_selected=True, is_present=True).first()
        ArtworkFile.objects.filter(library=library, relative_path__in=replaced).update(is_present=False, is_selected=False)
        ArtworkFile.objects.filter(**target, artwork_type=artwork_type, is_selected=True).update(is_selected=False)
        artwork, _created = ArtworkFile.objects.update_or_create(
            library=library,
            relative_path=relative,
            defaults={
                "target_type": resolved.field_state_type,
                "target_id": resolved.obj.id,
                "artwork_type": artwork_type,
                "source_name": PurePosixPath(relative).stem,
                "file_name": PurePosixPath(relative).name,
                "extension": PurePosixPath(relative).suffix.lstrip("."),
                "size_bytes": size,
                "modified_ns": modified_ns,
                "is_present": True,
                "is_selected": True,
                "last_seen_at": timezone.now(),
            },
        )
        snapshot = {"path": relative, "sha256": sha, "url": item.url, "provider": row["provider"]}
        CanonicalFieldState.objects.update_or_create(
            target_type=resolved.field_state_type,
            target_id=resolved.obj.id,
            field_name=f"artwork_{artwork_type}",
            defaults={
                "source": CanonicalFieldState.Source.PROVIDER,
                "source_ref": source_ref,
                "value_snapshot": snapshot,
                "locked": False,
                "updated_by": user,
            },
        )
        return MetadataChangeSet.objects.create(
            target_type=resolved.field_state_type,
            target_id=resolved.obj.id,
            source=MetadataChangeSet.Source.PROVIDER,
            source_ref=source_ref,
            operation_id=request["operation_id"],
            changes={
                f"artwork_{artwork_type}": {
                    "old": {"id": str(previous.id), "relative_path": previous.relative_path} if previous else None,
                    "new": {"id": str(artwork.id), "relative_path": relative},
                }
            },
            note=(
                f"Saved {artwork_type} artwork from {row['provider_label']}."
                + (f" Kept {len(backups)} previous file(s) as backups." if backups else "")
            ),
            changed_by=user,
            details={
                "artwork": True,
                "artwork_type": artwork_type,
                "path": relative,
                "provider": row["provider"],
                "provider_label": row["provider_label"],
                "connection_id": row["connection_id"],
                "connection_name": row["connection_name"],
                "source_id": request.get("source_id") or "",
                "ids": _clean_ids(request.get("ids")),
                "url": item.url,
                "width": width,
                "height": height,
                "sha256": sha,
                "replaced": replaced,
                "backups": backups,
                "retrieved_at": timezone.now().isoformat(),
            },
        )
