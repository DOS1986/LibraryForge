from pathlib import Path

import pytest

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient

from preferences.models import SystemAction


@pytest.mark.django_db
def test_health_is_public():
    client = APIClient()
    response = client.get("/api/system/health/")

    assert response.status_code == 200
    assert response.data["status"] == "ok"
    assert "runtime_started_at" in response.data


@pytest.mark.django_db
def test_non_staff_user_cannot_restart(tmp_path):
    user = get_user_model().objects.create_user(
        email="user@example.com",
        password="test-password",
    )

    client = APIClient()
    client.force_authenticate(user=user)

    restart_file = tmp_path / "restart.request"

    with override_settings(
        LIBRARYFORGE_RESTART_ENABLED=True,
        LIBRARYFORGE_RESTART_FILE=str(restart_file),
    ):
        response = client.post("/api/system/restart/")

    assert response.status_code == 403
    assert not restart_file.exists()


@pytest.mark.django_db
def test_staff_restart_creates_supervisor_request(tmp_path):
    user = get_user_model().objects.create_user(
        email="admin@example.com",
        password="test-password",
        is_staff=True,
    )

    client = APIClient()
    client.force_authenticate(user=user)

    restart_file = tmp_path / "restart.request"

    with override_settings(
        LIBRARYFORGE_RESTART_ENABLED=True,
        LIBRARYFORGE_RESTART_FILE=str(restart_file),
    ):
        response = client.post("/api/system/restart/")

    assert response.status_code == 202
    assert response.data["accepted"] is True
    assert Path(restart_file).exists()
    assert SystemAction.objects.filter(
        actor=user,
        action=SystemAction.Action.RESTART,
    ).exists()
