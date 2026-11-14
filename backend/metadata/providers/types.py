"""Normalized metadata-provider vocabulary.

These structures are LibraryForge's own representation of what an external
metadata provider returned. Provider adapters translate remote responses into
these types; matching, preview, and merge code must consume only these types
and never interpret provider JSON directly.

Nothing in this module writes catalog data. A ``MetadataCandidate`` or
``ProviderMetadata`` value is a proposal, not an approved change.
"""

from __future__ import annotations

import datetime
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse


class MetadataTargetType(StrEnum):
    """Catalog targets a metadata provider may search and describe.

    ``series`` is a television series as a whole, never an episode or season.
    """

    MOVIE = "movie"
    SERIES = "series"


METADATA_TARGET_TYPES: tuple[str, ...] = tuple(item.value for item in MetadataTargetType)


class MetadataErrorCategory(StrEnum):
    """Stable, provider-independent failure categories.

    An empty search result is *not* an error and has no category here.
    """

    UNSUPPORTED_TARGET = "unsupported_target"
    INVALID_REQUEST = "invalid_request"
    INVALID_CONFIGURATION = "invalid_configuration"
    INVALID_CREDENTIALS = "invalid_credentials"
    PERMISSION_DENIED = "permission_denied"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    MALFORMED_RESPONSE = "malformed_response"


_RETRYABLE_CATEGORIES = frozenset(
    {
        MetadataErrorCategory.RATE_LIMITED,
        MetadataErrorCategory.UNAVAILABLE,
        MetadataErrorCategory.TIMEOUT,
    }
)


class MetadataProviderError(Exception):
    """A sanitized provider failure safe to show to an authorized user.

    ``message`` must never contain credentials, request URLs carrying secrets,
    internal paths, or unfiltered upstream response bodies.
    """

    def __init__(
        self,
        category: MetadataErrorCategory | str,
        message: str,
        *,
        retry_after_seconds: int | None = None,
    ):
        self.category = MetadataErrorCategory(category)
        self.message = message
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message)

    @property
    def retryable(self) -> bool:
        return self.category in _RETRYABLE_CATEGORIES

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "category": self.category.value,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.retry_after_seconds is not None:
            payload["retry_after_seconds"] = self.retry_after_seconds
        return payload


def parse_target_type(value: MetadataTargetType | str) -> MetadataTargetType:
    try:
        return MetadataTargetType(str(value).strip().casefold())
    except ValueError as exc:
        raise MetadataProviderError(
            MetadataErrorCategory.UNSUPPORTED_TARGET,
            f"Unsupported metadata target type: {str(value)[:32]!r}",
        ) from exc


# ---------------------------------------------------------------------------
# Field bounds and helpers
# ---------------------------------------------------------------------------

MAX_TITLE_LENGTH = 512
MAX_OVERVIEW_LENGTH = 20_000
MAX_TAGLINE_LENGTH = 1_000
MAX_SHORT_TEXT_LENGTH = 128
MAX_URL_LENGTH = 2_048
MAX_COLLECTION_ITEMS = 100
MAX_EXTERNAL_IDS = 50
MAX_ARTWORK_ITEMS = 200
MAX_RAW_BYTES = 256 * 1024
MAX_RUNTIME_MINUTES = 100_000
MAX_IMAGE_DIMENSION = 100_000

_SOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_NAMESPACE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,31}$")
_LANGUAGE_PATTERN = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean_text(value: Any, *, name: str, max_length: int, multiline: bool = False) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text.")  # noqa: TRY004 - one ValueError contract for adapters
    text = _CONTROL_CHARACTERS.sub("", value)
    if not multiline:
        text = " ".join(text.split())
    text = text.strip()
    if len(text) > max_length:
        raise ValueError(f"{name} exceeds {max_length} characters.")
    return text


def validate_source_id(value: Any) -> str:
    text = str(value).strip() if isinstance(value, (str, int)) and not isinstance(value, bool) else ""
    if not _SOURCE_ID_PATTERN.fullmatch(text):
        raise ValueError("source_id must be 1-128 characters of letters, digits, '.', '_', ':' or '-'.")
    return text


def _clean_language(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not _LANGUAGE_PATTERN.fullmatch(value.strip()):
        raise ValueError("language must be a BCP 47 style language tag.")
    return value.strip()


def _clean_url(value: Any, *, name: str) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text.")  # noqa: TRY004
    url = value.strip()
    if len(url) > MAX_URL_LENGTH:
        raise ValueError(f"{name} exceeds {MAX_URL_LENGTH} characters.")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{name} must be an absolute http(s) URL.")
    if parsed.username or parsed.password:
        raise ValueError(f"{name} must not embed credentials.")
    return url


def _clean_names(values: Any, *, name: str) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise ValueError(f"{name} must be a list of names.")  # noqa: TRY004
    output: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = _clean_text(item, name=name, max_length=MAX_SHORT_TEXT_LENGTH)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    if len(output) > MAX_COLLECTION_ITEMS:
        raise ValueError(f"{name} exceeds {MAX_COLLECTION_ITEMS} entries.")
    return tuple(output)


def _optional_int(value: Any, *, name: str, minimum: int, maximum: int) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer.")  # noqa: TRY004
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PartialDate:
    """A date that preserves its known precision.

    A bare year stays a year: ``PartialDate(1999)`` does not mean 1999-01-01.
    """

    year: int
    month: int | None = None
    day: int | None = None

    def __post_init__(self) -> None:
        if self.year is None:
            raise ValueError("year is required.")
        _optional_int(self.year, name="year", minimum=1800, maximum=2200)
        _optional_int(self.month, name="month", minimum=1, maximum=12)
        _optional_int(self.day, name="day", minimum=1, maximum=31)
        if self.day is not None and self.month is None:
            raise ValueError("day requires month.")
        if self.day is not None:
            datetime.date(self.year, self.month, self.day)

    def _sort_key(self) -> tuple[int, int, int]:
        return (self.year, self.month or 0, self.day or 0)

    def definitely_before(self, other: PartialDate) -> bool:
        """True only when ``self`` is earlier than ``other`` at their shared precision."""

        depth = min(len(self.isoformat().split("-")), len(other.isoformat().split("-")))
        return self._sort_key()[:depth] < other._sort_key()[:depth]

    @property
    def precision(self) -> str:
        if self.day is not None:
            return "day"
        if self.month is not None:
            return "month"
        return "year"

    def isoformat(self) -> str:
        parts = [f"{self.year:04d}"]
        if self.month is not None:
            parts.append(f"{self.month:02d}")
        if self.day is not None:
            parts.append(f"{self.day:02d}")
        return "-".join(parts)

    @classmethod
    def parse(cls, value: Any) -> PartialDate | None:
        """Parse ``YYYY``, ``YYYY-MM`` or ``YYYY-MM-DD``; empty values are ``None``."""

        if value in (None, ""):
            return None
        if isinstance(value, PartialDate):
            return value
        if not isinstance(value, str):
            raise ValueError("Dates must be ISO 8601 text.")  # noqa: TRY004
        match = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", value.strip())
        if not match:
            raise ValueError("Dates must use YYYY, YYYY-MM or YYYY-MM-DD.")
        year, month, day = match.groups()
        try:
            return cls(int(year), int(month) if month else None, int(day) if day else None)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid calendar date.") from exc


@dataclass(frozen=True, slots=True)
class ExternalId:
    """A namespaced identifier such as ``("imdb", "tt0133093")``."""

    namespace: str
    value: str

    def __post_init__(self) -> None:
        namespace = str(self.namespace or "").strip().casefold()
        if not _NAMESPACE_PATTERN.fullmatch(namespace):
            raise ValueError("External ID namespace must be 1-32 lowercase letters, digits, '_', '.' or '-'.")
        value = _clean_text(self.value, name="External ID value", max_length=MAX_SHORT_TEXT_LENGTH)
        if not value:
            raise ValueError("External ID value is required.")
        object.__setattr__(self, "namespace", namespace)
        object.__setattr__(self, "value", value)

    def to_dict(self) -> dict[str, str]:
        return {"namespace": self.namespace, "value": self.value}


def _clean_external_ids(values: Any) -> tuple[ExternalId, ...]:
    if values is None:
        return ()
    if isinstance(values, Mapping):
        values = [ExternalId(str(key), str(value)) for key, value in values.items() if value not in (None, "")]
    output: list[ExternalId] = []
    by_namespace: dict[str, str] = {}
    for item in values:
        if not isinstance(item, ExternalId):
            raise ValueError("external_ids must contain ExternalId values.")  # noqa: TRY004
        existing = by_namespace.get(item.namespace)
        if existing is None:
            by_namespace[item.namespace] = item.value
            output.append(item)
        elif existing != item.value:
            raise ValueError(f"Conflicting external IDs for namespace {item.namespace!r}.")
    if len(output) > MAX_EXTERNAL_IDS:
        raise ValueError(f"external_ids exceeds {MAX_EXTERNAL_IDS} entries.")
    return tuple(output)


class ArtworkKind(StrEnum):
    POSTER = "poster"
    BACKDROP = "backdrop"
    LOGO = "logo"
    THUMBNAIL = "thumbnail"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class ProviderArtwork:
    """A discovered artwork reference.

    The URL is a discovery reference only: it is not downloaded, validated as
    an image, or selected. Download must go through the hardened remote-artwork
    path with origin restrictions. Unknown dimensions and language stay ``None``.
    """

    url: str
    kind: ArtworkKind | str = ArtworkKind.OTHER
    width: int | None = None
    height: int | None = None
    language: str | None = None

    def __post_init__(self) -> None:
        url = _clean_url(self.url, name="Artwork URL")
        if not url:
            raise ValueError("Artwork URL is required.")
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "kind", ArtworkKind(self.kind))
        _optional_int(self.width, name="Artwork width", minimum=1, maximum=MAX_IMAGE_DIMENSION)
        _optional_int(self.height, name="Artwork height", minimum=1, maximum=MAX_IMAGE_DIMENSION)
        object.__setattr__(self, "language", _clean_language(self.language))

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "kind": self.kind.value,
            "width": self.width,
            "height": self.height,
            "language": self.language,
        }


@dataclass(frozen=True, slots=True)
class MetadataIdentity:
    """Provider-scoped identity. A source ID alone is not globally unique."""

    provider: str
    target_type: MetadataTargetType
    source_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "target_type": self.target_type.value,
            "source_id": self.source_id,
        }


def _validate_identity(instance: Any) -> None:
    provider = str(instance.provider or "").strip()
    if not _NAMESPACE_PATTERN.fullmatch(provider):
        raise ValueError("provider must be a registered provider key.")
    object.__setattr__(instance, "provider", provider)
    object.__setattr__(instance, "target_type", parse_target_type(instance.target_type))
    object.__setattr__(instance, "source_id", validate_source_id(instance.source_id))


@dataclass(frozen=True, slots=True)
class MetadataCandidate:
    """A lightweight search result used to compare plausible matches.

    It is enough to choose a candidate and fetch details; it is not a complete
    catalog record and must never be applied directly.
    """

    provider: str
    target_type: MetadataTargetType | str
    source_id: str
    title: str
    original_title: str = ""
    release_date: PartialDate | None = None
    overview: str = ""
    artwork_url: str = ""
    external_ids: tuple[ExternalId, ...] = ()

    def __post_init__(self) -> None:
        _validate_identity(self)
        title = _clean_text(self.title, name="title", max_length=MAX_TITLE_LENGTH)
        if not title:
            raise ValueError("Candidate title is required.")
        object.__setattr__(self, "title", title)
        object.__setattr__(
            self,
            "original_title",
            _clean_text(self.original_title, name="original_title", max_length=MAX_TITLE_LENGTH),
        )
        object.__setattr__(self, "release_date", PartialDate.parse(self.release_date))
        object.__setattr__(
            self,
            "overview",
            _clean_text(self.overview, name="overview", max_length=MAX_OVERVIEW_LENGTH, multiline=True),
        )
        object.__setattr__(self, "artwork_url", _clean_url(self.artwork_url, name="artwork_url"))
        object.__setattr__(self, "external_ids", _clean_external_ids(self.external_ids))

    @property
    def identity(self) -> MetadataIdentity:
        return MetadataIdentity(self.provider, self.target_type, self.source_id)

    @property
    def year(self) -> int | None:
        return self.release_date.year if self.release_date else None

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.identity.to_dict(),
            "title": self.title,
            "original_title": self.original_title,
            "release_date": self.release_date.isoformat() if self.release_date else None,
            "year": self.year,
            "overview": self.overview,
            "artwork_url": self.artwork_url,
            "external_ids": [item.to_dict() for item in self.external_ids],
        }


@dataclass(frozen=True, slots=True)
class ContentRating:
    """A certification for one territory (ISO 3166-1 alpha-2, e.g. ``US``).

    This is a content/age rating, never an audience score.
    """

    value: str
    territory: str = ""

    def __post_init__(self) -> None:
        value = _clean_text(self.value, name="Content rating", max_length=32)
        if not value:
            raise ValueError("Content rating value is required.")
        territory = str(self.territory or "").strip().upper()
        if territory and not re.fullmatch(r"[A-Z]{2}", territory):
            raise ValueError("Content rating territory must be an ISO 3166-1 alpha-2 code.")
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "territory", territory)

    def to_dict(self) -> dict[str, str]:
        return {"value": self.value, "territory": self.territory}


@dataclass(frozen=True, slots=True)
class ProviderMetadata:
    """Normalized detail data for one provider record.

    Empty values mean "the provider did not supply this"; they never mean
    "clear the catalog field". Empty collections never imply removal.

    ``runtime_minutes`` is a movie's running time. For series it is a typical
    episode runtime, which the merge layer must not treat as a movie runtime
    without an explicit policy.

    ``raw`` is optional bounded diagnostic data. It is untrusted, internal,
    excluded from ``to_dict()``, and must never be used as a merge source or
    contain credentials.
    """

    provider: str
    target_type: MetadataTargetType | str
    source_id: str
    title: str
    original_title: str = ""
    sort_title: str = ""
    overview: str = ""
    tagline: str = ""
    release_date: PartialDate | None = None
    end_date: PartialDate | None = None
    runtime_minutes: int | None = None
    content_ratings: tuple[ContentRating, ...] = ()
    genres: tuple[str, ...] = ()
    studios: tuple[str, ...] = ()
    networks: tuple[str, ...] = ()
    external_ids: tuple[ExternalId, ...] = ()
    artwork: tuple[ProviderArtwork, ...] = ()
    raw: Mapping[str, Any] | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        _validate_identity(self)
        title = _clean_text(self.title, name="title", max_length=MAX_TITLE_LENGTH)
        if not title:
            raise ValueError("Metadata title is required.")
        object.__setattr__(self, "title", title)
        for name in ("original_title", "sort_title"):
            object.__setattr__(
                self, name, _clean_text(getattr(self, name), name=name, max_length=MAX_TITLE_LENGTH)
            )
        object.__setattr__(
            self,
            "overview",
            _clean_text(self.overview, name="overview", max_length=MAX_OVERVIEW_LENGTH, multiline=True),
        )
        object.__setattr__(
            self, "tagline", _clean_text(self.tagline, name="tagline", max_length=MAX_TAGLINE_LENGTH)
        )
        release_date = PartialDate.parse(self.release_date)
        end_date = PartialDate.parse(self.end_date)
        if end_date is not None and self.target_type != MetadataTargetType.SERIES:
            raise ValueError("end_date is only valid for series.")
        if release_date and end_date and end_date.definitely_before(release_date):
            raise ValueError("end_date precedes release_date.")
        object.__setattr__(self, "release_date", release_date)
        object.__setattr__(self, "end_date", end_date)
        _optional_int(self.runtime_minutes, name="runtime_minutes", minimum=1, maximum=MAX_RUNTIME_MINUTES)

        ratings = tuple(self.content_ratings or ())
        if not all(isinstance(item, ContentRating) for item in ratings):
            raise ValueError("content_ratings must contain ContentRating values.")
        territories = [item.territory for item in ratings]
        if len(territories) != len(set(territories)):
            raise ValueError("content_ratings must have at most one rating per territory.")
        object.__setattr__(self, "content_ratings", ratings)

        for name in ("genres", "studios", "networks"):
            object.__setattr__(self, name, _clean_names(getattr(self, name), name=name))
        object.__setattr__(self, "external_ids", _clean_external_ids(self.external_ids))

        artwork = tuple(self.artwork or ())
        if not all(isinstance(item, ProviderArtwork) for item in artwork):
            raise ValueError("artwork must contain ProviderArtwork values.")
        if len(artwork) > MAX_ARTWORK_ITEMS:
            raise ValueError(f"artwork exceeds {MAX_ARTWORK_ITEMS} entries.")
        object.__setattr__(self, "artwork", tuple(dict.fromkeys(artwork)))

        if self.raw is not None:
            if not isinstance(self.raw, Mapping):
                raise ValueError("raw must be a mapping.")
            try:
                encoded = json.dumps(self.raw, default=str)
            except (TypeError, ValueError) as exc:
                raise ValueError("raw must be JSON serializable.") from exc
            if len(encoded.encode("utf-8")) > MAX_RAW_BYTES:
                object.__setattr__(self, "raw", None)

    @property
    def identity(self) -> MetadataIdentity:
        return MetadataIdentity(self.provider, self.target_type, self.source_id)

    @property
    def year(self) -> int | None:
        return self.release_date.year if self.release_date else None

    def to_dict(self) -> dict[str, Any]:
        """Browser-safe representation. ``raw`` is deliberately excluded."""

        return {
            **self.identity.to_dict(),
            "title": self.title,
            "original_title": self.original_title,
            "sort_title": self.sort_title,
            "overview": self.overview,
            "tagline": self.tagline,
            "release_date": self.release_date.isoformat() if self.release_date else None,
            "release_date_precision": self.release_date.precision if self.release_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "year": self.year,
            "runtime_minutes": self.runtime_minutes,
            "content_ratings": [item.to_dict() for item in self.content_ratings],
            "genres": list(self.genres),
            "studios": list(self.studios),
            "networks": list(self.networks),
            "external_ids": [item.to_dict() for item in self.external_ids],
            "artwork": [item.to_dict() for item in self.artwork],
        }


def deduplicate_candidates(candidates: Iterable[MetadataCandidate]) -> list[MetadataCandidate]:
    """Drop repeated (provider, target_type, source_id) identities, keeping order."""

    seen: set[MetadataIdentity] = set()
    output: list[MetadataCandidate] = []
    for candidate in candidates:
        if candidate.identity not in seen:
            seen.add(candidate.identity)
            output.append(candidate)
    return output
