from __future__ import annotations

from integrations.providers.base import (
    ALLOWED_CAPABILITIES,
    ALLOWED_CREDENTIAL_MODES,
    CAPABILITY_METADATA,
    IntegrationProvider,
    provider_supports_metadata_target,
)
from integrations.providers.tmdb import TMDbProvider
from integrations.providers.tubearchivist import TubeArchivistProvider
from integrations.providers.youtube import YouTubeProvider
from metadata.providers.types import METADATA_TARGET_TYPES, MetadataTargetType

PROVIDERS: dict[str, type[IntegrationProvider]] = {
    YouTubeProvider.definition.key: YouTubeProvider,
    TubeArchivistProvider.definition.key: TubeArchivistProvider,
    TMDbProvider.definition.key: TMDbProvider,
}


def _validate_definition(provider_class: type[IntegrationProvider]) -> None:
    definition = provider_class.definition
    invalid_capabilities = set(definition.capabilities) - ALLOWED_CAPABILITIES
    if invalid_capabilities:
        raise ValueError(
            f"Provider {definition.key} has unsupported capabilities: {sorted(invalid_capabilities)}"
        )
    if definition.credential_mode not in ALLOWED_CREDENTIAL_MODES:
        raise ValueError(
            f"Provider {definition.key} has unsupported credential mode: {definition.credential_mode}"
        )
    invalid_targets = set(definition.metadata_target_types) - set(METADATA_TARGET_TYPES)
    if invalid_targets:
        raise ValueError(
            f"Provider {definition.key} has unsupported metadata target types: {sorted(invalid_targets)}"
        )
    if definition.metadata_target_types and CAPABILITY_METADATA not in definition.capabilities:
        raise ValueError(
            f"Provider {definition.key} declares metadata target types without the metadata capability"
        )


def get_provider_class(provider: str) -> type[IntegrationProvider]:
    try:
        return PROVIDERS[provider]
    except KeyError as exc:
        raise ValueError(f"Unsupported integration provider: {provider}") from exc


def provider_catalog() -> list[dict]:
    rows: list[dict] = []
    for provider_class in PROVIDERS.values():
        _validate_definition(provider_class)
        definition = provider_class.definition
        rows.append(
            {
                "key": definition.key,
                "label": definition.label,
                "description": definition.description,
                "capabilities": list(definition.capabilities),
                "online_video": definition.online_video,
                "storage_policy": definition.storage_policy,
                "credential_mode": definition.credential_mode,
                "credential_summary": definition.credential_summary,
                "metadata_target_types": list(definition.metadata_target_types),
                "attribution": definition.attribution,
                "fields": [
                    {
                        "name": field.name,
                        "label": field.label,
                        "secret": field.secret,
                        "required": field.required,
                        "placeholder": field.placeholder,
                        "help_text": field.help_text,
                    }
                    for field in definition.fields
                ],
            }
        )
    return sorted(rows, key=lambda row: row["label"].casefold())


def metadata_provider_classes(target_type: MetadataTargetType | str) -> list[type[IntegrationProvider]]:
    """Registered providers whose definition supports a metadata target type.

    This is catalog discovery only. It does not imply that any connection for
    these providers is enabled, assigned to a library, or usable by a user.
    """

    output: list[type[IntegrationProvider]] = []
    for provider_class in PROVIDERS.values():
        _validate_definition(provider_class)
        if provider_supports_metadata_target(provider_class.definition, target_type):
            output.append(provider_class)
    return output
