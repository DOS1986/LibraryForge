from django.contrib import admin

from django.urls import (
    include,
    path,
)

from rest_framework.routers import (
    DefaultRouter,
)

from catalog.artwork_views import (
    artwork_content,
    artwork_select,
    library_artwork_refresh,
)

from catalog.editor_views import (
    episode_editor,
    media_version_editor,
    media_version_make_primary,
    movie_editor,
    season_editor,
    series_editor,
)

from catalog.online_video_views import (
    ChannelCatalogViewSet,
    OnlineVideoCatalogViewSet,
    PlaylistCatalogViewSet,
)

from catalog.views import (
    EpisodeCatalogViewSet,
    MovieCatalogViewSet,
    SeasonCatalogViewSet,
    SemanticMatchViewSet,
    SeriesCatalogViewSet,
)

from jobs.views import ScanJobViewSet
from libraries.views import LibraryViewSet

from libraryforge.system_views import (
    system_health,
    system_restart,
    system_status,
    system_version,
)

from media.browser_views import (
    LibraryBrowserViewSet,
)

from media.views import (
    LibraryAssetViewSet,
    MediaFileViewSet,
    MediaItemViewSet,
)

from metadata.views import (
    MetadataSourceViewSet,
    NfoFileViewSet,
)

from outputs.views import (
    OutputProfileViewSet,
    ProjectionViewSet,
)


router = DefaultRouter()

router.register(
    "libraries",
    LibraryViewSet,
    basename="library",
)

router.register(
    "catalog-movies",
    MovieCatalogViewSet,
    basename="catalog-movie",
)

router.register(
    "catalog-series",
    SeriesCatalogViewSet,
    basename="catalog-series",
)

router.register(
    "catalog-seasons",
    SeasonCatalogViewSet,
    basename="catalog-season",
)

router.register(
    "catalog-episodes",
    EpisodeCatalogViewSet,
    basename="catalog-episode",
)

router.register(
    "catalog-channels",
    ChannelCatalogViewSet,
    basename="catalog-channel",
)

router.register(
    "catalog-playlists",
    PlaylistCatalogViewSet,
    basename="catalog-playlist",
)

router.register(
    "catalog-online-videos",
    OnlineVideoCatalogViewSet,
    basename="catalog-online-video",
)

router.register(
    "semantic-matches",
    SemanticMatchViewSet,
    basename="semantic-match",
)

router.register(
    "library-assets",
    LibraryAssetViewSet,
    basename="library-asset",
)

router.register(
    "library-browser",
    LibraryBrowserViewSet,
    basename="library-browser",
)

router.register(
    "media-files",
    MediaFileViewSet,
    basename="media-file",
)

router.register(
    "media-items",
    MediaItemViewSet,
    basename="media-item",
)

router.register(
    "scan-jobs",
    ScanJobViewSet,
    basename="scan-job",
)

router.register(
    "metadata-sources",
    MetadataSourceViewSet,
    basename="metadata-source",
)

router.register(
    "nfo-files",
    NfoFileViewSet,
    basename="nfo-file",
)

router.register(
    "output-profiles",
    OutputProfileViewSet,
    basename="output-profile",
)

router.register(
    "projections",
    ProjectionViewSet,
    basename="projection",
)


urlpatterns = [
    path(
        "admin/",
        admin.site.urls,
    ),

    path(
        "api/auth/",
        include(
            "accounts.urls"
        ),
    ),

    path(
        "api/system/version/",
        system_version,
        name="system-version",
    ),

    path(
        "api/system/health/",
        system_health,
        name="system-health",
    ),

    path(
        "api/system/status/",
        system_status,
        name="system-status",
    ),

    path(
        "api/system/restart/",
        system_restart,
        name="system-restart",
    ),

    path(
        "api/preferences/",
        include(
            "preferences.urls"
        ),
    ),

    path(
        "api/integrations/",
        include(
            "integrations.urls"
        ),
    ),


    path(
        "api/artwork-files/<uuid:artwork_id>/content/",
        artwork_content,
        name="artwork-file-content",
    ),

    path(
        "api/artwork-files/<uuid:artwork_id>/select/",
        artwork_select,
        name="artwork-file-select",
    ),

    path(
        "api/libraries/<uuid:library_id>/artwork/refresh/",
        library_artwork_refresh,
        name="library-artwork-refresh",
    ),

    path(
        "api/catalog-editor/movies/<uuid:item_id>/",
        movie_editor,
        name="catalog-editor-movie",
    ),

    path(
        "api/catalog-editor/series/<uuid:series_id>/",
        series_editor,
        name="catalog-editor-series",
    ),

    path(
        "api/catalog-editor/seasons/<uuid:season_id>/",
        season_editor,
        name="catalog-editor-season",
    ),

    path(
        "api/catalog-editor/episodes/<uuid:episode_id>/",
        episode_editor,
        name="catalog-editor-episode",
    ),

    path(
        "api/catalog-editor/versions/<uuid:version_id>/",
        media_version_editor,
        name="catalog-editor-version",
    ),

    path(
        "api/catalog-editor/versions/<uuid:version_id>/make-primary/",
        media_version_make_primary,
        name="catalog-editor-version-primary",
    ),

    path(
        "api/",
        include(
            router.urls
        ),
    ),
]
