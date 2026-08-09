from rest_framework import serializers

from libraries.services.storage import (
    validate_storage_path as
    validate_server_storage_path,
)

from .models import Library


class LibrarySerializer(
    serializers.ModelSerializer
):
    management_mode_label = (
        serializers.CharField(
            source=(
                "get_management_mode_display"
            ),
            read_only=True,
        )
    )

    content_type_label = (
        serializers.CharField(
            source=(
                "get_content_type_display"
            ),
            read_only=True,
        )
    )

    media_count = (
        serializers.SerializerMethodField()
    )

    class Meta:
        model = Library

        fields = [
            "id",
            "name",
            "path",
            "management_mode",
            "management_mode_label",
            "content_type",
            "content_type_label",
            "media_count",
            "last_scanned_at",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "management_mode_label",
            "content_type_label",
            "media_count",
            "last_scanned_at",
            "created_at",
            "updated_at",
        ]

    def get_media_count(
        self,
        obj,
    ):
        return (
            obj.media_files
            .filter(
                is_present=True
            )
            .count()
        )

    def validate_name(
        self,
        value,
    ):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Library name cannot be empty."
            )

        return value

    def validate_path(
        self,
        value,
    ):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Library path cannot be empty."
            )

        try:
            validate_server_storage_path(
                value
            )

        except (
            OSError,
            ValueError,
        ) as exc:
            raise serializers.ValidationError(
                str(exc)
            ) from exc

        return value
