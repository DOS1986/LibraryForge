"""Metadata-provider contracts shared by integration adapters and metadata services."""

from metadata.providers.types import (
    METADATA_TARGET_TYPES,
    ArtworkKind,
    ContentRating,
    ExternalId,
    MetadataCandidate,
    MetadataErrorCategory,
    MetadataIdentity,
    MetadataProviderError,
    MetadataTargetType,
    PartialDate,
    ProviderArtwork,
    ProviderMetadata,
    deduplicate_candidates,
    parse_target_type,
)

__all__ = [
    "METADATA_TARGET_TYPES",
    "ArtworkKind",
    "ContentRating",
    "ExternalId",
    "MetadataCandidate",
    "MetadataErrorCategory",
    "MetadataIdentity",
    "MetadataProviderError",
    "MetadataTargetType",
    "PartialDate",
    "ProviderArtwork",
    "ProviderMetadata",
    "deduplicate_candidates",
    "parse_target_type",
]
