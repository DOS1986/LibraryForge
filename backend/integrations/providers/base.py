from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from metadata.providers.types import (
    MetadataCandidate,
    MetadataErrorCategory,
    MetadataIdentity,
    MetadataProviderError,
    MetadataTargetType,
    ProviderMetadata,
    deduplicate_candidates,
    parse_target_type,
    validate_source_id,
)

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
    # Normalized catalog targets (see metadata.providers.types.MetadataTargetType)
    # this provider can search and describe. Empty means the provider only
    # supports its existing known-ID lookups (lookup_one/lookup_many).
    metadata_target_types: tuple[str, ...] = ()
    # Notice the provider's terms require wherever its data is shown.
    attribution: str = ""
    # External-ID namespace of this provider's source IDs ("tmdb", "imdb"), so
    # an item that already has that ID can be looked up directly.
    metadata_id_namespace: str = ""


MAX_METADATA_QUERY_LENGTH = 200
MAX_METADATA_RESULTS = 50
MAX_METADATA_PAGE = 100


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

    # ------------------------------------------------------------------
    # Normalized metadata contract (movie / series search and details)
    #
    # The public methods validate the request *before* any network call and
    # validate the adapter's normalized output afterwards. Adapters implement
    # only _search_metadata and _get_metadata. Neither path may write catalog
    # data; callers own target authorization, preview, and apply.
    # ------------------------------------------------------------------

    def supports_metadata_target(self, target_type: MetadataTargetType | str) -> bool:
        return provider_supports_metadata_target(self.definition, target_type)

    def _require_metadata_target(self, target_type: MetadataTargetType | str) -> MetadataTargetType:
        parsed = parse_target_type(target_type)
        if not self.supports_metadata_target(parsed):
            raise MetadataProviderError(
                MetadataErrorCategory.UNSUPPORTED_TARGET,
                f"{self.definition.label} does not provide {parsed.value} metadata.",
            )
        return parsed

    def search_metadata(
        self,
        *,
        target_type: MetadataTargetType | str,
        query: str,
        year: int | None = None,
        language: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> list[MetadataCandidate]:
        """Search for movie or series candidates.

        An empty list is a successful "no results" answer. Failures raise
        ``MetadataProviderError`` with a stable category.
        """

        parsed = self._require_metadata_target(target_type)
        cleaned_query = " ".join(str(query or "").split())
        if not cleaned_query or len(cleaned_query) > MAX_METADATA_QUERY_LENGTH:
            raise MetadataProviderError(
                MetadataErrorCategory.INVALID_REQUEST,
                f"Search text must be 1-{MAX_METADATA_QUERY_LENGTH} characters.",
            )
        if year is not None and (isinstance(year, bool) or not isinstance(year, int) or not 1800 <= year <= 2200):
            raise MetadataProviderError(MetadataErrorCategory.INVALID_REQUEST, "Year must be between 1800 and 2200.")
        if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= MAX_METADATA_PAGE:
            raise MetadataProviderError(
                MetadataErrorCategory.INVALID_REQUEST, f"Page must be between 1 and {MAX_METADATA_PAGE}."
            )
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_METADATA_RESULTS:
            raise MetadataProviderError(
                MetadataErrorCategory.INVALID_REQUEST, f"Limit must be between 1 and {MAX_METADATA_RESULTS}."
            )
        cleaned_language = self._clean_metadata_language(language)

        results = self._search_metadata(
            target_type=parsed,
            query=cleaned_query,
            year=year,
            language=cleaned_language,
            page=page,
            limit=limit,
        )
        if not isinstance(results, list) or not all(isinstance(item, MetadataCandidate) for item in results):
            raise self._malformed("search results")
        for item in results:
            if item.provider != self.definition.key or item.target_type != parsed:
                raise self._malformed("search results")
        return deduplicate_candidates(results)[:limit]

    def get_metadata(
        self,
        *,
        target_type: MetadataTargetType | str,
        source_id: str,
        language: str | None = None,
    ) -> ProviderMetadata:
        """Fetch normalized details for one provider record."""

        parsed = self._require_metadata_target(target_type)
        try:
            cleaned_source_id = validate_source_id(source_id)
        except ValueError as exc:
            raise MetadataProviderError(MetadataErrorCategory.INVALID_REQUEST, str(exc)) from exc
        cleaned_language = self._clean_metadata_language(language)

        result = self._get_metadata(target_type=parsed, source_id=cleaned_source_id, language=cleaned_language)
        if not isinstance(result, ProviderMetadata):
            raise self._malformed("metadata details")
        if result.identity != MetadataIdentity(self.definition.key, parsed, cleaned_source_id):
            raise self._malformed("metadata details")
        return result

    def _search_metadata(
        self,
        *,
        target_type: MetadataTargetType,
        query: str,
        year: int | None,
        language: str | None,
        page: int,
        limit: int,
    ) -> list[MetadataCandidate]:
        raise NotImplementedError

    def _get_metadata(
        self,
        *,
        target_type: MetadataTargetType,
        source_id: str,
        language: str | None,
    ) -> ProviderMetadata:
        raise NotImplementedError

    @staticmethod
    def _clean_metadata_language(language: str | None) -> str | None:
        if language in (None, ""):
            return None
        if not isinstance(language, str) or not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", language):
            raise MetadataProviderError(MetadataErrorCategory.INVALID_REQUEST, "Language must be a language tag.")
        return language

    def _malformed(self, what: str) -> MetadataProviderError:
        return MetadataProviderError(
            MetadataErrorCategory.MALFORMED_RESPONSE,
            f"{self.definition.label} returned malformed {what}.",
        )


def provider_supports_metadata_target(
    definition: ProviderDefinition,
    target_type: MetadataTargetType | str,
) -> bool:
    """Catalog-level check: capability declared and target type declared.

    This says what a provider *can* do. It does not grant access to any
    connection; callers must still check the connection, library assignment,
    and user authorization.
    """

    if CAPABILITY_METADATA not in definition.capabilities:
        return False
    try:
        parsed = parse_target_type(target_type)
    except MetadataProviderError:
        return False
    return parsed.value in definition.metadata_target_types
