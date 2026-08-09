from django.contrib import admin

from django.urls import (
    include,
    path,
)

from rest_framework.routers import (
    DefaultRouter,
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
        "api/",
        include(
            router.urls
        ),
    ),
]
