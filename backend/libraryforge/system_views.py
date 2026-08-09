from django.conf import settings

from rest_framework.decorators import (
    api_view,
    permission_classes,
)

from rest_framework.permissions import (
    IsAuthenticated,
)

from rest_framework.response import (
    Response,
)

from libraryforge.versioning import (
    get_version_info,
)


@api_view(
    [
        "GET",
    ]
)
@permission_classes(
    [
        IsAuthenticated,
    ]
)
def system_version(
    request,
):
    environment = (
        "development"
        if settings.DEBUG
        else "production"
    )

    return Response(
        get_version_info(
            environment=environment
        )
    )
