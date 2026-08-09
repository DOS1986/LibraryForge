from rest_framework.exceptions import (
    ValidationError,
)

from rest_framework.pagination import (
    PageNumberPagination,
)

from rest_framework.response import (
    Response,
)


class LibraryForgePagination(
    PageNumberPagination
):
    page_size = 20

    page_size_query_param = (
        "page_size"
    )

    max_page_size = 100

    allowed_page_sizes = (
        10,
        20,
        50,
        100,
    )

    def get_page_size(
        self,
        request,
    ):
        raw_value = (
            request.query_params
            .get(
                self.page_size_query_param
            )
        )

        if raw_value is None:
            return self.page_size

        try:
            page_size = int(
                raw_value
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ValidationError(
                {
                    "page_size": (
                        "Page size must be "
                        "10, 20, 50, or 100."
                    )
                }
            ) from exc

        if (
            page_size
            not in self.allowed_page_sizes
        ):
            raise ValidationError(
                {
                    "page_size": (
                        "Page size must be "
                        "10, 20, 50, or 100."
                    )
                }
            )

        return page_size

    def get_paginated_response(
        self,
        data,
    ):
        return Response(
            {
                "count":
                    self.page
                    .paginator
                    .count,

                "page":
                    self.page.number,

                "page_size":
                    self.get_page_size(
                        self.request
                    ),

                "total_pages":
                    self.page
                    .paginator
                    .num_pages,

                "next":
                    self.get_next_link(),

                "previous":
                    self.get_previous_link(),

                "results":
                    data,
            }
        )
