import uuid

from django.db.models import (
    CharField,
    UUIDField,
    F,
    Q,
    Value,
)

from rest_framework import (
    filters,
    mixins,
    permissions,
    viewsets,
)

from rest_framework.exceptions import (
    ValidationError,
)

from libraryforge.pagination import (
    LibraryForgePagination,
)

from metadata.models import NfoFile

from catalog.models import ArtworkFile

from .models import (
    MediaFile,
    MediaItem,
)

from .serializers import (
    LibraryAssetSerializer,
    MediaFileSerializer,
    MediaItemDetailSerializer,
)


class LibraryAssetViewSet(
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = (
        LibraryAssetSerializer
    )

    permission_classes = [
        permissions.IsAuthenticated,
    ]

    pagination_class = (
        LibraryForgePagination
    )

    allowed_ordering = {
        "relative_path",
        "file_name",
        "size_bytes",
        "asset_type",
        "media_title",
        "channel_title",
        "metadata_status",
    }

    def get_queryset(self):
        library_id = (
            self.request
            .query_params
            .get(
                "library"
            )
        )

        if not library_id:
            raise ValidationError(
                {
                    "library":
                        (
                            "A library ID "
                            "is required."
                        )
                }
            )

        try:
            parsed_id = uuid.UUID(
                library_id
            )

        except ValueError as exc:
            raise ValidationError(
                {
                    "library":
                        "Invalid library ID."
                }
            ) from exc

        search = (
            self.request
            .query_params
            .get(
                "search",
                "",
            )
            .strip()
        )

        ordering = (
            self.request
            .query_params
            .get(
                "ordering",
                "relative_path",
            )
        )

        descending = (
            ordering.startswith("-")
        )

        ordering_field = (
            ordering[1:]
            if descending
            else ordering
        )

        if (
            ordering_field
            not in self.allowed_ordering
        ):
            ordering_field = (
                "relative_path"
            )

            descending = False

        ordering_expression = (
            f"-{ordering_field}"
            if descending
            else ordering_field
        )

        media_queryset = (
            MediaFile.objects
            .filter(
                library_id=parsed_id,
                library__owner=(
                    self.request.user
                ),
            )
        )

        nfo_queryset = (
            NfoFile.objects
            .filter(
                library_id=parsed_id,
                library__owner=(
                    self.request.user
                ),
            )
        )

        artwork_queryset = (
            ArtworkFile.objects
            .filter(
                library_id=parsed_id,
                library__owner=(
                    self.request.user
                ),
            )
        )

        if search:
            media_queryset = (
                media_queryset
                .filter(
                    Q(
                        relative_path__icontains=(
                            search
                        )
                    )
                    | Q(
                        file_name__icontains=(
                            search
                        )
                    )
                    | Q(
                        media_item__title__icontains=(
                            search
                        )
                    )
                    | Q(
                        media_item__online_video__channel__title__icontains=(
                            search
                        )
                    )
                )
            )

            nfo_queryset = (
                nfo_queryset
                .filter(
                    Q(
                        relative_path__icontains=(
                            search
                        )
                    )
                    | Q(
                        file_name__icontains=(
                            search
                        )
                    )
                    | Q(
                        media_item__title__icontains=(
                            search
                        )
                    )
                    | Q(
                        media_item__online_video__channel__title__icontains=(
                            search
                        )
                    )
                )
            )

            artwork_queryset = (
                artwork_queryset
                .filter(
                    Q(
                        relative_path__icontains=(
                            search
                        )
                    )
                    | Q(
                        file_name__icontains=(
                            search
                        )
                    )
                    | Q(
                        artwork_type__icontains=(
                            search
                        )
                    )
                )
            )

        media_values = (
            media_queryset
            .annotate(
                media_title=F(
                    "media_item__title"
                ),

                channel_id=F(
                    "media_item__online_video__channel_id"
                ),

                channel_title=F(
                    "media_item__online_video__channel__title"
                ),

                asset_type=Value(
                    "media",
                    output_field=(
                        CharField()
                    ),
                ),

                metadata_status=F(
                    "probe_status"
                ),
            )
            .values(
                "id",
                "library",
                "media_item",
                "media_title",
                "channel_id",
                "channel_title",
                "asset_type",
                "relative_path",
                "file_name",
                "size_bytes",
                "is_present",
                "metadata_status",
            )
        )

        nfo_values = (
            nfo_queryset
            .annotate(
                media_title=F(
                    "media_item__title"
                ),

                channel_id=F(
                    "media_item__online_video__channel_id"
                ),

                channel_title=F(
                    "media_item__online_video__channel__title"
                ),

                asset_type=Value(
                    "nfo",
                    output_field=(
                        CharField()
                    ),
                ),

                metadata_status=F(
                    "parse_status"
                ),
            )
            .values(
                "id",
                "library",
                "media_item",
                "media_title",
                "channel_id",
                "channel_title",
                "asset_type",
                "relative_path",
                "file_name",
                "size_bytes",
                "is_present",
                "metadata_status",
            )
        )

        artwork_values = (
            artwork_queryset
            .annotate(
                media_item=Value(
                    None,
                    output_field=(
                        UUIDField()
                    ),
                ),

                media_title=Value(
                    "",
                    output_field=(
                        CharField()
                    ),
                ),

                channel_id=Value(
                    None,
                    output_field=(
                        UUIDField()
                    ),
                ),

                channel_title=Value(
                    "",
                    output_field=(
                        CharField()
                    ),
                ),

                asset_type=Value(
                    "artwork",
                    output_field=(
                        CharField()
                    ),
                ),

                metadata_status=F(
                    "artwork_type"
                ),
            )
            .values(
                "id",
                "library",
                "media_item",
                "media_title",
                "channel_id",
                "channel_title",
                "asset_type",
                "relative_path",
                "file_name",
                "size_bytes",
                "is_present",
                "metadata_status",
            )
        )

        return (
            media_values
            .union(
                nfo_values,
                artwork_values,
                all=True,
            )
            .order_by(
                ordering_expression,
                "id",
            )
        )


class MediaFileViewSet(
    viewsets.ReadOnlyModelViewSet
):
    serializer_class = MediaFileSerializer

    permission_classes = [
        permissions.IsAuthenticated,
    ]

    pagination_class = (
        LibraryForgePagination
    )

    filter_backends = [
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    search_fields = [
        "file_name",
        "relative_path",
        "media_item__title",
        "media_item__online_video__channel__title",
        "video_codec",
    ]

    ordering_fields = [
        "media_item__title",
        "media_item__online_video__channel__title",
        "video_codec",
        "duration_seconds",
        "size_bytes",
        "source_modified_at",
        "relative_path",
    ]

    ordering = [
        "media_item__title",
        "relative_path",
    ]

    def get_queryset(self):
        queryset = (
            MediaFile.objects
            .filter(
                library__owner=(
                    self.request.user
                )
            )
            .select_related(
                "media_item",
                "media_item__online_video",
                "media_item__online_video__channel",
                "library",
            )
        )

        library_id = self.request.query_params.get(
            "library"
        )

        if library_id:
            try:
                parsed_id = uuid.UUID(
                    library_id
                )

            except ValueError as exc:
                raise ValidationError(
                    {
                        "library":
                            "Invalid library ID."
                    }
                ) from exc

            queryset = queryset.filter(
                library_id=parsed_id
            )

        return queryset


class MediaItemViewSet(
    viewsets.ReadOnlyModelViewSet
):
    serializer_class = (
        MediaItemDetailSerializer
    )

    permission_classes = [
        permissions.IsAuthenticated,
    ]

    def get_queryset(self):
        return (
            MediaItem.objects
            .filter(
                library__owner=(
                    self.request.user
                )
            )
            .select_related("library")
            .prefetch_related(
                "files",
                "metadata_sources",
            )
        )
