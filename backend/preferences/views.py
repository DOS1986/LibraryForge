from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from preferences.models import UserSettings
from preferences.serializers import UserSettingsSerializer


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def user_settings(request):
    settings_record, _ = UserSettings.objects.get_or_create(
        user=request.user
    )

    if request.method == "GET":
        return Response(
            UserSettingsSerializer(settings_record).data
        )

    serializer = UserSettingsSerializer(
        settings_record,
        data=request.data,
        partial=True,
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()

    return Response(serializer.data)
