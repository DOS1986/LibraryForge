"""Mocked Jellyfin server tests. No network access."""

from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from integrations.crypto import encrypt_secrets
from integrations.models import IntegrationConnection, LibraryIntegration
from integrations.providers.http import ProviderHttpError
from integrations.providers.jellyfin import JellyfinProvider
from integrations.security import public_provider_error
from libraries.models import Library
from metadata.providers import MetadataErrorCategory, MetadataProviderError

KEY = "0123456789abcdef0123456789abcdef"
MOVIES_ID = "a" * 32
TV_ID = "b" * 32
KID_ID = "c" * 32
ADMIN_ID = "d" * 32

LIBRARIES = [
    {"Name": "Movies", "Locations": ["/media/Movies"], "CollectionType": "movies", "ItemId": MOVIES_ID},
    {"Name": "Shows", "Locations": ["/media/TVShows", "/extra/tv"], "CollectionType": "tvshows", "ItemId": TV_ID},
    {"Name": "Broken", "Locations": [], "ItemId": "not-an-id"},
]

USERS = [
    {"Name": "Admin", "Id": ADMIN_ID, "Policy": {"IsAdministrator": True, "MaxParentalRating": None}},
    {"Name": "Son", "Id": KID_ID, "Policy": {
        "IsAdministrator": False, "MaxParentalRating": 5, "BlockUnratedItems": ["Movie"],
    }},
    {"Name": "Bad", "Id": "x"},
]

RATINGS = [{"Name": "PG", "Value": 5}, {"Name": "TV-PG", "Value": 5}, {"Name": "R", "Value": 9}]


def fake_jellyfin(url, **kwargs):
    parsed = urlparse(url)
    params = {key: value[0] for key, value in parse_qs(parsed.query).items()}
    path = parsed.path
    if path == "/System/Info":
        return {"ServerName": "Home", "Version": "10.10.7", "Id": "srv"}
    if path == "/Library/VirtualFolders":
        return LIBRARIES
    if path == "/Users":
        return USERS
    if path == "/Localization/ParentalRatings":
        return RATINGS
    if path == "/Items":
        totals = {
            (KID_ID, "Movie", False): 100,
            (KID_ID, "Movie", True): 0,
            (KID_ID, "Series", False): 40,
            (KID_ID, "Series", True): 7,
        }
        key = (params["userId"], params["includeItemTypes"], params.get("hasOfficialRating") == "false")
        return {"Items": [], "TotalRecordCount": totals.get(key, 500)}
    if path.endswith("/Refresh"):
        return None
    raise AssertionError(f"unexpected {url}")


class _JellyfinCase(SimpleTestCase):
    def setUp(self):
        self.provider = JellyfinProvider(configuration={"base_url": "http://jelly.local:8096/"}, secrets={"api_key": KEY})
        patcher = patch("integrations.providers.jellyfin.request_json", side_effect=fake_jellyfin)
        self.request = patcher.start()
        self.addCleanup(patcher.stop)

    def last(self):
        call = self.request.call_args_list[-1]
        parsed = urlparse(call.args[0])
        return parsed, {key: value[0] for key, value in parse_qs(parsed.query).items()}, call.kwargs


class AdapterTests(_JellyfinCase):
    def test_validation(self):
        for config, secrets in (
            ({"base_url": "ftp://x"}, {"api_key": KEY}),
            ({"base_url": "http://user:pw@x"}, {"api_key": KEY}),
            ({"base_url": "http://x?a=1"}, {"api_key": KEY}),
            ({"base_url": "http://x"}, {"api_key": "short"}),
        ):
            with self.subTest(config=config), self.assertRaises(ValueError):
                JellyfinProvider(configuration=config, secrets=secrets).validate()

    def test_auth_header_and_connection_test(self):
        result = self.provider.test_connection()
        parsed, _params, kwargs = self.last()
        self.assertEqual((parsed.netloc, parsed.path), ("jelly.local:8096", "/System/Info"))
        self.assertEqual(kwargs["headers"], {"Authorization": f'MediaBrowser Token="{KEY}"'})
        self.assertNotIn(KEY, parsed.geturl())
        self.assertIn("10.10.7", result["message"])

    def test_libraries_skip_malformed_entries(self):
        libraries = self.provider.libraries()
        self.assertEqual([item["id"] for item in libraries], [MOVIES_ID, TV_ID])
        self.assertEqual(libraries[1]["locations"], ["/media/TVShows", "/extra/tv"])

    def test_refresh_is_a_non_destructive_scan(self):
        self.provider.refresh_library(TV_ID)
        parsed, params, kwargs = self.last()
        self.assertEqual(parsed.path, f"/Items/{TV_ID}/Refresh")
        self.assertEqual(kwargs["method"], "POST")
        self.assertEqual(params["ReplaceAllMetadata"], "false")
        self.assertEqual(params["MetadataRefreshMode"], "Default")
        self.assertEqual(params["Recursive"], "true")
        with self.assertRaises(MetadataProviderError):
            self.provider.refresh_library("../../System/Shutdown")

    def test_parental_report(self):
        report = self.provider.parental_report()
        son, admin = report["users"]
        self.assertEqual(son["name"], "Son")
        self.assertEqual(son["max_parental_rating"], 5)
        self.assertEqual(son["max_parental_rating_names"], ["PG", "TV-PG"])
        self.assertEqual(son["blocks_unrated"], ["Movie"])
        self.assertEqual(son["counts"]["movies"], {"visible": 100, "visible_unrated": 0})
        self.assertEqual(son["counts"]["series"], {"visible": 40, "visible_unrated": 7})
        self.assertEqual(len(son["warnings"]), 1)
        self.assertIn("7 unrated TV series", son["warnings"][0])
        self.assertTrue(admin["is_administrator"])
        self.assertEqual(admin["warnings"], [])

    def test_errors_are_mapped_and_secret_free(self):
        for error, category in (
            (ProviderHttpError("x", status=401), MetadataErrorCategory.INVALID_CREDENTIALS),
            (ProviderHttpError("x", status=403), MetadataErrorCategory.PERMISSION_DENIED),
            (ProviderHttpError("x", reason="timeout"), MetadataErrorCategory.TIMEOUT),
            (ProviderHttpError("x", reason="unreachable"), MetadataErrorCategory.UNAVAILABLE),
        ):
            self.request.side_effect = error
            with self.subTest(category=category), self.assertRaises(MetadataProviderError) as ctx:
                self.provider.test_connection()
            self.assertEqual(ctx.exception.category, category)
            self.assertNotIn(KEY, public_provider_error(ctx.exception))


class ApiTests(APITestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(email="owner@example.com", password="password")
        self.other = user_model.objects.create_user(email="other@example.com", password="password")
        self.client.force_authenticate(self.user)
        self.tv = Library.objects.create(
            owner=self.user, name="TV Shows", path=r"\\10.10.1.178\media-library\TVShows", content_type="tv"
        )
        self.connection = IntegrationConnection.objects.create(
            owner=self.user, name="Jellyfin", provider="jellyfin",
            configuration={"base_url": "http://jelly.local:8096"}, encrypted_secrets=encrypt_secrets({"api_key": KEY}),
        )
        self.link = LibraryIntegration.objects.create(library=self.tv, connection=self.connection, capabilities=["output"])
        patcher = patch("integrations.providers.jellyfin.request_json", side_effect=fake_jellyfin)
        self.request = patcher.start()
        self.addCleanup(patcher.stop)

    def url(self, suffix=""):
        return f"/api/integrations/library-links/{self.link.id}/jellyfin/{suffix}"

    def test_suggests_library_by_folder_name_across_path_styles(self):
        data = self.client.get(self.url()).data
        self.assertEqual(data["suggested_id"], TV_ID)
        self.assertIsNone(data["selected_id"])
        self.assertEqual(len(data["libraries"]), 2)

    def test_save_link_and_refresh(self):
        self.assertEqual(self.client.post(self.url("refresh/")).status_code, 400)
        response = self.client.post(self.url(), {"jellyfin_library_id": TV_ID}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.link.refresh_from_db()
        self.assertEqual(self.link.options, {"jellyfin_library_id": TV_ID})
        self.assertEqual(self.client.get("/api/integrations/library-links/").data[0]["options"], self.link.options)
        refresh = self.client.post(self.url("refresh/"))
        self.assertEqual(refresh.status_code, 200, refresh.data)
        self.assertTrue(urlparse(self.request.call_args_list[-1].args[0]).path.endswith(f"/Items/{TV_ID}/Refresh"))
        self.assertEqual(self.client.post(self.url(), {"jellyfin_library_id": "f" * 32}, format="json").status_code, 400)
        self.client.post(self.url(), {"jellyfin_library_id": ""}, format="json")
        self.link.refresh_from_db()
        self.assertEqual(self.link.options, {})

    def test_refresh_requires_output_capability_and_enabled_link(self):
        self.link.options = {"jellyfin_library_id": TV_ID}
        self.link.capabilities = []
        self.link.save()
        self.assertEqual(self.client.post(self.url("refresh/")).status_code, 400)
        self.link.capabilities = ["output"]
        self.link.enabled = False
        self.link.save()
        self.assertEqual(self.client.post(self.url("refresh/")).status_code, 400)

    def test_parental_report_endpoint(self):
        response = self.client.get(f"/api/integrations/connections/{self.connection.id}/jellyfin/parental/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["users"][0]["name"], "Son")

    def test_scoping(self):
        theirs = IntegrationConnection.objects.create(
            owner=self.other, name="J", provider="jellyfin", configuration={"base_url": "http://x"},
            encrypted_secrets=encrypt_secrets({"api_key": KEY}),
        )
        self.assertEqual(self.client.get(f"/api/integrations/connections/{theirs.id}/jellyfin/parental/").status_code, 404)
        tmdb = IntegrationConnection.objects.create(
            owner=self.user, name="TMDB", provider="tmdb", configuration={},
            encrypted_secrets=encrypt_secrets({"access_token": "t" * 40}),
        )
        tmdb_link = LibraryIntegration.objects.create(library=self.tv, connection=tmdb, capabilities=["metadata"])
        self.assertEqual(self.client.get(f"/api/integrations/library-links/{tmdb_link.id}/jellyfin/").status_code, 404)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url()).status_code, (401, 403))

    def test_jellyfin_errors_are_reported(self):
        self.request.side_effect = ProviderHttpError("x", status=401)
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["detail"], "Jellyfin rejected the API key.")
