import pytest

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from preferences.models import UserSettings


@pytest.mark.django_db
def test_user_settings_are_created_and_persisted():
    user = get_user_model().objects.create_user(
        email="settings@example.com",
        password="test-password",
    )

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get("/api/preferences/settings/")
    assert response.status_code == 200
    assert response.data["default_page_size"] == 20
    assert UserSettings.objects.filter(user=user).exists()

    response = client.patch(
        "/api/preferences/settings/",
        {
            "display_name": "Test User",
            "default_page_size": 50,
            "show_build_information": False,
            "needs_attention_unresolved_sort": "confidence",
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["display_name"] == "Test User"
    assert response.data["default_page_size"] == 50
    assert response.data["show_build_information"] is False

    settings_record = UserSettings.objects.get(user=user)
    assert settings_record.display_name == "Test User"
    assert settings_record.default_page_size == 50
