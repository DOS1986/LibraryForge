from rest_framework import serializers

from preferences.models import UserSettings


ALLOWED_ATTENTION_SORTS = {
    "media_file__file_name",
    "-media_file__file_name",
    "media_file__relative_path",
    "-media_file__relative_path",
    "status",
    "-status",
    "source",
    "-source",
    "confidence",
    "-confidence",
    "media_file__media_item__title",
    "-media_file__media_item__title",
    "media_file__duration_seconds",
    "-media_file__duration_seconds",
    "media_file__size_bytes",
    "-media_file__size_bytes",
    "updated_at",
    "-updated_at",
}


class UserSettingsSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        source="user.email",
        read_only=True,
    )

    is_staff = serializers.BooleanField(
        source="user.is_staff",
        read_only=True,
    )

    is_superuser = serializers.BooleanField(
        source="user.is_superuser",
        read_only=True,
    )

    class Meta:
        model = UserSettings
        fields = [
            "display_name",
            "email",
            "is_staff",
            "is_superuser",
            "default_page_size",
            "needs_attention_unresolved_sort",
            "needs_attention_conflict_sort",
            "needs_attention_confirmed_sort",
            "show_build_information",
            "confirm_restart",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "email",
            "is_staff",
            "is_superuser",
            "created_at",
            "updated_at",
        ]

    def validate_default_page_size(self, value):
        if value not in {10, 20, 50, 100}:
            raise serializers.ValidationError(
                "Use 10, 20, 50, or 100."
            )

        return value

    def _validate_attention_sort(self, value):
        if value not in ALLOWED_ATTENTION_SORTS:
            raise serializers.ValidationError(
                "Unsupported Needs Attention sort."
            )

        return value

    def validate_needs_attention_unresolved_sort(self, value):
        return self._validate_attention_sort(value)

    def validate_needs_attention_conflict_sort(self, value):
        return self._validate_attention_sort(value)

    def validate_needs_attention_confirmed_sort(self, value):
        return self._validate_attention_sort(value)
