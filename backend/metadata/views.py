from rest_framework import (
    filters,
    permissions,
    status,
    viewsets,
)

from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from libraryforge.pagination import (
    LibraryForgePagination,
)

from metadata.services.nfo import (
    parse_nfo_content,
    write_nfo_file,
)

from .models import (
    MetadataSource,
    NfoFile,
)

from .serializers import (
    MetadataSourceSerializer,
    NfoFileSerializer,
)


class MetadataSourceViewSet(
    viewsets.ReadOnlyModelViewSet
):
    serializer_class = MetadataSourceSerializer

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
        "media_item__title",
        "media_file__file_name",
        "media_file__relative_path",
    ]

    ordering_fields = [
        "media_item__title",
        "source_type",
        "status",
        "last_checked_at",
    ]

    ordering = [
        "media_item__title",
        "source_type",
    ]

    def get_queryset(self):
        queryset = (
            MetadataSource.objects
            .filter(
                media_file__library__owner=(
                    self.request.user
                )
            )
            .select_related(
                "media_item",
                "media_file",
                "media_file__library",
            )
        )

        library_id = self.request.query_params.get(
            "library"
        )

        source_type = self.request.query_params.get(
            "source_type"
        )

        source_status = self.request.query_params.get(
            "status"
        )

        if library_id:
            queryset = queryset.filter(
                media_file__library_id=(
                    library_id
                )
            )

        if source_type:
            queryset = queryset.filter(
                source_type=source_type
            )

        if source_status:
            queryset = queryset.filter(
                status=source_status
            )

        return queryset


class NfoFileViewSet(
    viewsets.ModelViewSet
):
    serializer_class = NfoFileSerializer

    permission_classes = [
        permissions.IsAuthenticated,
    ]

    pagination_class = (
        LibraryForgePagination
    )

    http_method_names = [
        "get",
        "patch",
        "put",
        "head",
        "options",
    ]

    filter_backends = [
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    search_fields = [
        "file_name",
        "relative_path",
        "title",
        "media_item__title",
    ]

    ordering_fields = [
        "file_name",
        "title",
        "media_item__title",
        "year",
        "parse_status",
        "size_bytes",
        "updated_at",
        "relative_path",
    ]

    ordering = [
        "relative_path",
    ]

    def get_queryset(self):
        queryset = (
            NfoFile.objects
            .filter(
                library__owner=(
                    self.request.user
                )
            )
            .select_related(
                "library",
                "media_item",
                "media_file",
            )
        )

        library_id = self.request.query_params.get(
            "library"
        )

        if library_id:
            queryset = queryset.filter(
                library_id=library_id
            )

        return queryset

    def update(
        self,
        request,
        *args,
        **kwargs,
    ):
        nfo_file = self.get_object()

        raw_xml = request.data.get(
            "raw_xml"
        )

        if raw_xml is None:
            raise ValidationError(
                {
                    "raw_xml":
                        (
                            "raw_xml is "
                            "required."
                        )
                }
            )

        try:
            write_nfo_file(
                nfo_file,
                str(raw_xml),
            )

        except PermissionError as exc:
            raise ValidationError(
                {
                    "raw_xml":
                        str(exc)
                }
            ) from exc

        except ValueError as exc:
            raise ValidationError(
                {
                    "raw_xml":
                        (
                            "Invalid NFO: "
                            f"{exc}"
                        )
                }
            ) from exc

        serializer = self.get_serializer(
            nfo_file
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="validate",
    )
    def validate_nfo(
        self,
        request,
    ):
        raw_xml = request.data.get(
            "raw_xml",
            "",
        )

        parsed = parse_nfo_content(
            str(raw_xml)
        )

        return Response(
            {
                "valid":
                    (
                        parsed["status"]
                        == NfoFile
                        .ParseStatus
                        .OK
                    ),

                "root_element":
                    parsed[
                        "root_element"
                    ],

                "title":
                    parsed[
                        "title"
                    ],

                "year":
                    parsed[
                        "year"
                    ],

                "parsed_data":
                    parsed[
                        "parsed_data"
                    ],

                "error":
                    parsed[
                        "error"
                    ],
            }
        )
