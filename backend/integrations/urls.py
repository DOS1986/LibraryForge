from django.urls import include, path
from rest_framework.routers import DefaultRouter

from integrations.jellyfin_views import (
    jellyfin_link_view,
    jellyfin_parental_view,
    jellyfin_refresh_view,
)
from integrations.views import (
    IntegrationConnectionViewSet,
    LibraryIntegrationViewSet,
    library_artwork,
    providers,
    target_lookup,
)


router = DefaultRouter()
router.register("connections", IntegrationConnectionViewSet, basename="integration-connection")
router.register("library-links", LibraryIntegrationViewSet, basename="library-integration")

urlpatterns = [
    path("providers/", providers, name="integration-providers"),
    path(
        "libraries/<uuid:library_id>/lookup/<str:target_type>/<uuid:target_id>/",
        target_lookup,
        name="integration-target-lookup",
    ),
    path(
        "libraries/<uuid:library_id>/artwork/",
        library_artwork,
        name="integration-library-artwork",
    ),
    path("library-links/<uuid:link_id>/jellyfin/", jellyfin_link_view, name="jellyfin-link"),
    path("library-links/<uuid:link_id>/jellyfin/refresh/", jellyfin_refresh_view, name="jellyfin-refresh"),
    path("connections/<uuid:connection_id>/jellyfin/parental/", jellyfin_parental_view, name="jellyfin-parental"),
    path("", include(router.urls)),
]
