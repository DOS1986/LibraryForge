from __future__ import annotations

from integrations.providers.base import (
    ALLOWED_CAPABILITIES,
    ALLOWED_CREDENTIAL_MODES,
    IntegrationProvider,
)
from integrations.providers.tubearchivist import TubeArchivistProvider
from integrations.providers.youtube import YouTubeProvider


PROVIDERS: dict[str, type[IntegrationProvider]] = {
    YouTubeProvider.definition.key: YouTubeProvider,
    TubeArchivistProvider.definition.key: TubeArchivistProvider,
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
