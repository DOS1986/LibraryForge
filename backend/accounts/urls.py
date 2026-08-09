from django.urls import path

from . import api


urlpatterns = [
    path(
        "csrf/",
        api.csrf_token,
    ),

    path(
        "me/",
        api.current_user,
    ),

    path(
        "login/",
        api.login_view,
    ),

    path(
        "logout/",
        api.logout_view,
    ),
]