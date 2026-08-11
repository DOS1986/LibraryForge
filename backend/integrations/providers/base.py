from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings


CAPABILITY_METADATA = "metadata"
CAPABILITY_ARTWORK = "artwork"
CAPABILITY_CATALOG = "catalog"
CAPABILITY_OUTPUT = "output"

ALLOWED_CAPABILITIES = {
    CAPABILITY_METADATA,
    CAPABILITY_ARTWORK,
    CAPABILITY_CATALOG,
    CAPABILITY_OUTPUT,
}

CREDENTIAL_NONE = "none"
CREDENTIAL_USER = "user"
CREDENTIAL_APPLICATION = "application"
CREDENTIAL_HYBRID = "hybrid"

ALLOWED_CREDENTIAL_MODES = {
    CREDENTIAL_NONE,
    CREDENTIAL_USER,
    CREDENTIAL_APPLICATION,
    CREDENTIAL_HYBRID,
}


@dataclass(frozen=True)
class FieldDefinition:
    name: str
    label: str
    secret: bool = False
    required: bool = True
    placeholder: str = ""
    help_text: str = ""


@dataclass(frozen=True)
class ProviderDefinition:
    key: str
    label: str
    description: str
    capabilities: tuple[str, ...]
    fields: tuple[FieldDefinition, ...]
    online_video: bool = False
    storage_policy: str = "none"
    credential_mode: str = CREDENTIAL_USER
    credential_summary: str = "Credentials are supplied by the LibraryForge installation owner."
    application_secret_names: tuple[str, ...] = ()


class IntegrationProvider:
    definition: ProviderDefinition

    def __init__(self, *, configuration: dict[str, Any], secrets: dict[str, str]):
        self.configuration = configuration or {}
        self.secrets = secrets or {}
        self.application_secrets = self.get_application_credentials()

    def get_application_credentials(self) -> dict[str, str]:
        configured = getattr(settings, "LIBRARYFORGE_INTEGRATION_APPLICATION_CREDENTIALS", {}) or {}
        if not isinstance(configured, dict):
            return {}
        provider_values = configured.get(self.definition.key) or {}
        if not isinstance(provider_values, dict):
            return {}
        return {str(key): str(value) for key, value in provider_values.items() if value not in (None, "")}

    def validate(self) -> None:
        missing: list[str] = []
        for field in self.definition.fields:
            source = self.secrets if field.secret else self.configuration
            if field.required and not str(source.get(field.name, "")).strip():
                missing.append(field.label)

        missing_application = [
            name
            for name in self.definition.application_secret_names
            if not str(self.application_secrets.get(name, "")).strip()
        ]

        if missing:
            raise ValueError("Missing required integration settings: " + ", ".join(missing))
        if missing_application:
            raise ValueError(
                "LibraryForge application credentials are not configured for this provider: "
                + ", ".join(missing_application)
            )

    def test_connection(self) -> dict[str, Any]:
        raise NotImplementedError

    def lookup_many(self, *, target_type: str, source_ids: list[str]) -> dict[str, dict[str, Any]]:
        return {}

    def lookup_one(self, *, target_type: str, source_id: str) -> dict[str, Any] | None:
        results = self.lookup_many(target_type=target_type, source_ids=[source_id])
        return results.get(source_id)
