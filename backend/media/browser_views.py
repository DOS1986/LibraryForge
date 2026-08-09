import uuid

from rest_framework import (
    permissions,
    viewsets,
)

from rest_framework.exceptions import (
    ValidationError,
)

from libraryforge.pagination import (
    LibraryForgePagination,
)

from libraries.models import Library

from media.services.browser import (
    build_breadcrumbs,
    build_library_browser_entries,
    normalize_content_mode,
    normalize_folder_path,
)


class LibraryBrowserViewSet(
    viewsets.ViewSet
):
    permission_classes = [
        permissions.IsAuthenticated,
    ]

    pagination_class = (
        LibraryForgePagination
    )

    def list(
        self,
        request,
    ):
        library_id = (
            request
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

        try:
            current_path = (
                normalize_folder_path(
                    request
                    .query_params
                    .get(
                        "path",
                        "",
                    )
                )
            )

            content_mode = (
                normalize_content_mode(
                    request
                    .query_params
                    .get(
                        "content",
                        "media",
                    )
                )
            )

        except ValueError as exc:
            raise ValidationError(
                {
                    "detail":
                        str(exc)
                }
            ) from exc

        library = (
            Library.objects
            .filter(
                id=parsed_id,
                owner=request.user,
            )
            .first()
        )

        if library is None:
            raise ValidationError(
                {
                    "library":
                        "Library not found."
                }
            )

        search = (
            request
            .query_params
            .get(
                "search",
                "",
            )
            .strip()
            .casefold()
        )

        ordering = (
            request
            .query_params
            .get(
                "ordering",
                "name",
            )
        )

        entries = (
            build_library_browser_entries(
                library=library,
                current_path=current_path,
                content_mode=(
                    content_mode
                ),
                ordering=ordering,
            )
        )

        if search:
            entries = [
                entry
                for entry
                in entries
                if (
                    search
                    in (
                        entry
                        .get(
                            "name",
                            "",
                        )
                        .casefold()
                    )
                    or search
                    in (
                        entry
                        .get(
                            "title",
                            "",
                        )
                        .casefold()
                    )
                )
            ]

        paginator = (
            self.pagination_class()
        )

        page = (
            paginator.paginate_queryset(
                entries,
                request,
                view=self,
            )
        )

        response = (
            paginator
            .get_paginated_response(
                page
            )
        )

        response.data[
            "current_path"
        ] = current_path

        response.data[
            "breadcrumbs"
        ] = build_breadcrumbs(
            current_path
        )

        response.data[
            "content_mode"
        ] = content_mode

        response.data[
            "ordering"
        ] = ordering

        return response
