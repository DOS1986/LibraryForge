from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from integrations.crypto import decrypt_secrets, encrypt_secrets
from integrations.providers.base import (
    CREDENTIAL_APPLICATION,
    CREDENTIAL_USER,
    IntegrationProvider,
    ProviderDefinition,
)
from integrations.providers.tubearchivist import TubeArchivistProvider
from integrations.providers.youtube import YouTubeProvider
from integrations.registry import provider_catalog


@override_settings(SECRET_KEY="integration-test-secret")
class IntegrationCryptoTests(SimpleTestCase):
    def test_round_trip_does_not_store_plaintext(self):
        encrypted = encrypt_secrets({"api_key": "super-secret"})
        self.assertNotIn("super-secret", encrypted)
        self.assertEqual(
            decrypt_secrets(encrypted),
            {"api_key": "super-secret"},
        )


class _ApplicationCredentialProvider(IntegrationProvider):
    definition = ProviderDefinition(
        key="test-application-provider",
        label="Test Application Provider",
        description="Test provider",
        capabilities=("metadata",),
        fields=(),
        credential_mode=CREDENTIAL_APPLICATION,
        application_secret_names=("project_key",),
    )

    def test_connection(self):
        self.validate()
        return {"ok": True}


class ApplicationCredentialTests(SimpleTestCase):
    @override_settings(
        LIBRARYFORGE_INTEGRATION_APPLICATION_CREDENTIALS={
            "test-application-provider": {"project_key": "project-secret"}
        }
    )
    def test_provider_reads_application_credentials_from_settings(self):
        provider = _ApplicationCredentialProvider(configuration={}, secrets={})
        provider.validate()
        self.assertEqual(provider.application_secrets["project_key"], "project-secret")

    @override_settings(LIBRARYFORGE_INTEGRATION_APPLICATION_CREDENTIALS={})
    def test_provider_rejects_missing_required_application_credential(self):
        provider = _ApplicationCredentialProvider(configuration={}, secrets={})
        with self.assertRaisesRegex(ValueError, "project_key"):
            provider.validate()


class ProviderRegistryTests(SimpleTestCase):
    def test_registry_has_no_acquisition_capability(self):
        catalog = provider_catalog()
        self.assertEqual({row["key"] for row in catalog}, {"youtube", "tubearchivist"})
        for row in catalog:
            self.assertNotIn("acquisition", row["capabilities"])
            self.assertNotIn("download", row["capabilities"])
            self.assertEqual(row["credential_mode"], CREDENTIAL_USER)
            self.assertTrue(row["credential_summary"])

    @patch("integrations.providers.youtube.request_json")
    def test_youtube_lookup_prefers_highest_available_thumbnail(self, request_json):
        request_json.return_value = {
            "items": [
                {
                    "id": "UK4X75tY6_k",
                    "snippet": {
                        "title": "Example",
                        "description": "Description",
                        "channelId": "UChYpy_1syqfkN-x1wLkecAw",
                        "channelTitle": "Example Channel",
                        "thumbnails": {
                            "high": {"url": "https://img.example/high.jpg"},
                            "default": {"url": "https://img.example/default.jpg"},
                        },
                    },
                    "contentDetails": {"duration": "PT1M"},
                }
            ]
        }
        provider = YouTubeProvider(configuration={}, secrets={"api_key": "key"})
        result = provider.lookup_many(
            target_type="online_video",
            source_ids=["UK4X75tY6_k"],
        )
        self.assertEqual(
            result["UK4X75tY6_k"]["artwork_url"],
            "https://img.example/high.jpg",
        )

    @patch("integrations.providers.tubearchivist.request_json")
    def test_tubearchivist_normalizes_relative_artwork_url(self, request_json):
        request_json.return_value = {
            "channel_id": "UChYpy_1syqfkN-x1wLkecAw",
            "channel_thumb_url": "/cache/channels/example.jpg",
        }
        provider = TubeArchivistProvider(
            configuration={"base_url": "https://tube.example.test"},
            secrets={"api_token": "token"},
        )
        result = provider.lookup_one(
            target_type="channel",
            source_id="UChYpy_1syqfkN-x1wLkecAw",
        )
        self.assertEqual(
            result["artwork_url"],
            "https://tube.example.test/cache/channels/example.jpg",
        )
