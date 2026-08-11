from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase


class IntegrationApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="owner@example.com",
            password="password",
        )
        self.other_user = get_user_model().objects.create_user(
            email="other@example.com",
            password="password",
        )
        self.client.force_authenticate(self.user)

    def test_secret_is_write_only_and_provider_is_registry_driven(self):
        response = self.client.post(
            "/api/integrations/connections/",
            {
                "name": "YouTube Official",
                "provider": "youtube",
                "configuration": {},
                "secrets": {"api_key": "secret-key"},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["provider"], "youtube")
        self.assertEqual(response.data["provider_label"], "YouTube")
        self.assertEqual(response.data["configured_secret_fields"], ["api_key"])
        self.assertEqual(response.data["credential_mode"], "user")
        self.assertIn("own YouTube Data API", response.data["credential_summary"])
        self.assertNotIn("secrets", response.data)
        self.assertNotIn("encrypted_secrets", response.data)

    def test_connections_are_owner_scoped(self):
        from integrations.crypto import encrypt_secrets
        from integrations.models import IntegrationConnection

        IntegrationConnection.objects.create(
            owner=self.other_user,
            name="Other YouTube",
            provider="youtube",
            configuration={},
            encrypted_secrets=encrypt_secrets({"api_key": "other"}),
        )

        response = self.client.get("/api/integrations/connections/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_unknown_provider_is_rejected_without_schema_choices(self):
        response = self.client.post(
            "/api/integrations/connections/",
            {
                "name": "Unknown",
                "provider": "not-registered",
                "configuration": {},
                "secrets": {},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_provider_catalog_exposes_credential_ownership(self):
        response = self.client.get("/api/integrations/providers/")
        self.assertEqual(response.status_code, 200)
        providers = {row["key"]: row for row in response.data}
        self.assertEqual(providers["youtube"]["credential_mode"], "user")
        self.assertEqual(providers["tubearchivist"]["credential_mode"], "user")
        self.assertTrue(providers["youtube"]["credential_summary"])
        self.assertTrue(providers["tubearchivist"]["credential_summary"])
