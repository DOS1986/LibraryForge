from uuid import UUID

from django.db.models import (
    BigIntegerField,
    Case,
    Count,
    FloatField,
    IntegerField,
    Max,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.utils.dateparse import parse_date

from rest_framework import filters, permissions, viewsets
from rest_framework.exceptions import ValidationError

from catalog.models import (
    ArtworkFile,
    Channel,
    MediaVersion,
    OnlineVideo,
    Playlist,
    PlaylistMembership,
)
from catalog.online_video_serializers import (
    ChannelCatalogSerializer,
    OnlineVideoCatalogSerializer,
    PlaylistCatalogSerializer,
)
from integrations.services import apply_artwork_fallbacks
from libraryforge.pagination import LibraryForgePagination


PRESENT_VERSION_FILTER = Q(
    videos__media_item__versions__media_file__is_present=True
)
PRIMARY_PRESENT_VERSION_FILTER = Q(
    videos__media_item__versions__is_primary=True,
    videos__media_item__versions__media_file__is_present=True,
)

PLAYLIST_PRESENT_VERSION_FILTER = Q(
    memberships__online_video__media_item__versions__media_file__is_present=True
)
PLAYLIST_PRIMARY_PRESENT_VERSION_FILTER = Q(
    memberships__online_video__media_item__versions__is_primary=True,
    memberships__online_video__media_item__versions__media_file__is_present=True,
)


def _artwork_id_subquery(target_type, outer_field="pk"):
    return (
        ArtworkFile.objects
        .filter(
            target_type=target_type,
            target_id=OuterRef(outer_field),
            is_present=True,
            is_selected=True,
        )
        .annotate(
            artwork_rank=Case(
                When(
                    artwork_type=ArtworkFile.ArtworkType.PRIMARY,
                    then=Value(0),
                ),
                When(
                    artwork_type=ArtworkFile.ArtworkType.THUMB,
                    then=Value(1),
                ),
                When(
                    artwork_type=ArtworkFile.ArtworkType.BACKDROP,
                    then=Value(2),
                ),
                When(
                    artwork_type=ArtworkFile.ArtworkType.BANNER,
                    then=Value(3),
                ),
                default=Value(4),
                output_field=IntegerField(),
            )
        )
        .order_by("artwork_rank", "relative_path")
        .values("id")[:1]
    )


def _query_param(request, name):
    value = request.query_params.get(name)
    if value is None:
        return ""
    return str(value).strip()


def _uuid_query_param(request, name):
    value = _query_param(request, name)
    if not value:
        return ""

    try:
        UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({name: "Must be a valid UUID."}) from exc

    return value


def _date_query_param(request, name):
    value = _query_param(request, name)
    if not value:
        return None

    parsed = parse_date(value)
    if parsed is None:
        raise ValidationError({name: "Must be a valid YYYY-MM-DD date."})

    return parsed


def _choice_query_param(request, name, valid_values):
    value = _query_param(request, name)
    if not value:
        return ""

    if value not in valid_values:
        raise ValidationError({name: f"Unsupported value: {value}."})

    return value



class IntegrationArtworkMixin:
    integration_target_type = ""

    def _apply_integration_artwork(self, response):
        data = response.data
        if isinstance(data, dict):
            rows = data.get("results")
            if isinstance(rows, list):
                apply_artwork_fallbacks(
                    user=self.request.user,
                    rows=rows,
                    target_type=self.integration_target_type,
                )
            elif data.get("source_id"):
                apply_artwork_fallbacks(
                    user=self.request.user,
                    rows=[data],
                    target_type=self.integration_target_type,
                )
        elif isinstance(data, list):
            apply_artwork_fallbacks(
                user=self.request.user,
                rows=data,
                target_type=self.integration_target_type,
            )
        return response

    def list(self, request, *args, **kwargs):
        return self._apply_integration_artwork(
            super().list(request, *args, **kwargs)
        )

    def retrieve(self, request, *args, **kwargs):
        return self._apply_integration_artwork(
            super().retrieve(request, *args, **kwargs)
        )


class ChannelCatalogViewSet(IntegrationArtworkMixin, viewsets.ReadOnlyModelViewSet):
    integration_target_type = "channel"
    serializer_class = ChannelCatalogSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = LibraryForgePagination

    filter_backends = [
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    search_fields = [
        "title",
        "sort_title",
        "handle",
        "provider",
        "source_id",
        "semantic_key",
    ]
    ordering_fields = [
        "title",
        "sort_title",
        "provider",
        "video_count",
        "runtime_seconds",
        "storage_bytes",
        "last_upload_date",
        "created_at",
        "updated_at",
    ]
    ordering = ["sort_title", "title"]

    def get_queryset(self):
        queryset = (
            Channel.objects
            .filter(
                library__owner=self.request.user,
                videos__media_item__versions__media_file__is_present=True,
            )
            .annotate(
                artwork_id=Subquery(
                    _artwork_id_subquery(ArtworkFile.TargetType.CHANNEL)
                ),
                video_count=Count(
                    "videos",
                    filter=PRESENT_VERSION_FILTER,
                    distinct=True,
                ),
                runtime_seconds=Coalesce(
                    Sum(
                        "videos__media_item__versions__media_file__duration_seconds",
                        filter=PRIMARY_PRESENT_VERSION_FILTER,
                    ),
                    Value(0.0),
                    output_field=FloatField(),
                ),
                storage_bytes=Coalesce(
                    Sum(
                        "videos__media_item__versions__media_file__size_bytes",
                        filter=PRESENT_VERSION_FILTER,
                    ),
                    Value(0),
                    output_field=BigIntegerField(),
                ),
                last_upload_date=Max(
                    "videos__upload_date",
                    filter=PRESENT_VERSION_FILTER,
                ),
            )
            .distinct()
        )

        library_id = _uuid_query_param(self.request, "library")
        provider = _query_param(self.request, "provider")

        if library_id:
            queryset = queryset.filter(library_id=library_id)
        if provider:
            queryset = queryset.filter(provider=provider)

        return queryset


class PlaylistCatalogViewSet(IntegrationArtworkMixin, viewsets.ReadOnlyModelViewSet):
    integration_target_type = "playlist"
    serializer_class = PlaylistCatalogSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = LibraryForgePagination

    filter_backends = [
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    search_fields = [
        "title",
        "description",
        "provider",
        "source_id",
        "semantic_key",
        "channel__title",
        "channel__handle",
    ]
    ordering_fields = [
        "title",
        "provider",
        "playlist_kind",
        "channel__title",
        "video_count",
        "runtime_seconds",
        "storage_bytes",
        "created_at",
        "updated_at",
    ]
    ordering = ["title"]

    def get_queryset(self):
        queryset = (
            Playlist.objects
            .filter(
                library__owner=self.request.user,
                memberships__online_video__media_item__versions__media_file__is_present=True,
            )
            .select_related("channel")
            .annotate(
                artwork_id=Subquery(
                    _artwork_id_subquery(ArtworkFile.TargetType.PLAYLIST)
                ),
                video_count=Count(
                    "memberships__online_video",
                    filter=PLAYLIST_PRESENT_VERSION_FILTER,
                    distinct=True,
                ),
                runtime_seconds=Coalesce(
                    Sum(
                        (
                            "memberships__online_video__media_item__versions__"
                            "media_file__duration_seconds"
                        ),
                        filter=PLAYLIST_PRIMARY_PRESENT_VERSION_FILTER,
                    ),
                    Value(0.0),
                    output_field=FloatField(),
                ),
                storage_bytes=Coalesce(
                    Sum(
                        "memberships__online_video__media_item__versions__media_file__size_bytes",
                        filter=PLAYLIST_PRESENT_VERSION_FILTER,
                    ),
                    Value(0),
                    output_field=BigIntegerField(),
                ),
            )
            .distinct()
        )

        library_id = _uuid_query_param(self.request, "library")
        channel_id = _uuid_query_param(self.request, "channel")
        provider = _query_param(self.request, "provider")
        playlist_kind = _choice_query_param(
            self.request,
            "kind",
            {value for value, _label in Playlist.PlaylistKind.choices},
        )

        if library_id:
            queryset = queryset.filter(library_id=library_id)
        if channel_id:
            queryset = queryset.filter(channel_id=channel_id)
        if provider:
            queryset = queryset.filter(provider=provider)
        if playlist_kind:
            queryset = queryset.filter(playlist_kind=playlist_kind)

        return queryset


class OnlineVideoCatalogViewSet(IntegrationArtworkMixin, viewsets.ReadOnlyModelViewSet):
    integration_target_type = "online_video"
    serializer_class = OnlineVideoCatalogSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = LibraryForgePagination

    filter_backends = [
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    search_fields = [
        "media_item__title",
        "media_item__description",
        "media_item__semantic_key",
        "channel__title",
        "channel__handle",
        "provider",
        "source_id",
        "media_item__versions__media_file__file_name",
        "media_item__versions__media_file__relative_path",
    ]
    ordering_fields = [
        "media_item__title",
        "channel__title",
        "provider",
        "upload_date",
        "video_kind",
        "runtime_seconds",
        "storage_bytes",
        "version_count",
        "playlist_count",
        "playlist_memberships__position",
        "created_at",
        "updated_at",
    ]
    ordering = ["-upload_date", "media_item__title"]

    def get_queryset(self):
        present_versions = (
            MediaVersion.objects
            .filter(media_file__is_present=True)
            .select_related("media_file")
            .order_by("-is_primary", "created_at")
        )
        playlist_memberships = (
            PlaylistMembership.objects
            .select_related("playlist", "playlist__channel")
            .order_by("playlist__title", "position")
        )

        present_filter = Q(
            media_item__versions__media_file__is_present=True
        )
        primary_present_filter = Q(
            media_item__versions__is_primary=True,
            media_item__versions__media_file__is_present=True,
        )

        playlist_count_subquery = (
            PlaylistMembership.objects
            .filter(online_video_id=OuterRef("pk"))
            .values("online_video_id")
            .annotate(total=Count("playlist_id", distinct=True))
            .values("total")[:1]
        )

        queryset = (
            OnlineVideo.objects
            .filter(
                library__owner=self.request.user,
                media_item__versions__media_file__is_present=True,
            )
            .select_related("library", "media_item", "channel")
            .prefetch_related(
                Prefetch(
                    "media_item__versions",
                    queryset=present_versions,
                    to_attr="present_versions",
                ),
                Prefetch(
                    "playlist_memberships",
                    queryset=playlist_memberships,
                    to_attr="catalog_playlist_memberships",
                ),
            )
            .annotate(
                artwork_id=Subquery(
                    _artwork_id_subquery(
                        ArtworkFile.TargetType.MEDIA_ITEM,
                        outer_field="media_item_id",
                    )
                ),
                version_count=Count(
                    "media_item__versions",
                    filter=present_filter,
                    distinct=True,
                ),
                storage_bytes=Coalesce(
                    Sum(
                        "media_item__versions__media_file__size_bytes",
                        filter=present_filter,
                    ),
                    Value(0),
                    output_field=BigIntegerField(),
                ),
                runtime_seconds=Coalesce(
                    Max(
                        "media_item__versions__media_file__duration_seconds",
                        filter=primary_present_filter,
                    ),
                    Max(
                        "media_item__versions__media_file__duration_seconds",
                        filter=present_filter,
                    ),
                    output_field=FloatField(),
                ),
                playlist_count=Coalesce(
                    Subquery(
                        playlist_count_subquery,
                        output_field=IntegerField(),
                    ),
                    Value(0),
                    output_field=IntegerField(),
                ),
            )
            .distinct()
        )

        library_id = _uuid_query_param(self.request, "library")
        channel_id = _uuid_query_param(self.request, "channel")
        playlist_id = _uuid_query_param(self.request, "playlist")
        provider = _query_param(self.request, "provider")
        video_kind = _choice_query_param(
            self.request,
            "kind",
            {value for value, _label in OnlineVideo.VideoKind.choices},
        )
        uploaded_after = _date_query_param(self.request, "uploaded_after")
        uploaded_before = _date_query_param(self.request, "uploaded_before")

        if library_id:
            queryset = queryset.filter(library_id=library_id)
        if channel_id:
            queryset = queryset.filter(channel_id=channel_id)
        if playlist_id:
            queryset = queryset.filter(playlist_memberships__playlist_id=playlist_id)
        if provider:
            queryset = queryset.filter(provider=provider)
        if video_kind:
            queryset = queryset.filter(video_kind=video_kind)
        if uploaded_after:
            queryset = queryset.filter(upload_date__gte=uploaded_after)
        if uploaded_before:
            queryset = queryset.filter(upload_date__lte=uploaded_before)

        return queryset
