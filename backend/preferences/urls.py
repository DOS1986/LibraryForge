from django.urls import path

from preferences.views import user_settings


urlpatterns = [
    path(
        "settings/",
        user_settings,
        name="user-settings",
    ),
]
