from rest_framework import serializers

from .models import (
    MetadataSource,
    NfoFile,
)


class MetadataSourceSerializer(
    serializers.ModelSerializer
):
    source_type_label = serializers.CharField(
        source="get_source_type_display",
        read_only=True,
    )

    status_label = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    media_title = serializers.CharField(
        source="media_item.title",
        read_only=True,
    )

    media_item_id = serializers.UUIDField(
        source="media_item.id",
        read_only=True,
    )

    media_file_id = serializers.UUIDField(
        source="media_file.id",
        read_only=True,
    )

    file_name = serializers.CharField(
        source="media_file.file_name",
        read_only=True,
    )

    relative_path = serializers.CharField(
        source="media_file.relative_path",
        read_only=True,
    )

    library_id = serializers.UUIDField(
        source="media_file.library_id",
        read_only=True,
    )

    class Meta:
        model = MetadataSource

        fields = [
            "id",
            "library_id",
            "media_item_id",
            "media_file_id",
            "media_title",
            "file_name",
            "relative_path",
            "source_type",
            "source_type_label",
            "status",
            "status_label",
            "extracted_data",
            "error",
            "first_seen_at",
            "last_checked_at",
        ]

        read_only_fields = fields


class NfoFileSerializer(
    serializers.ModelSerializer
):
    media_title = serializers.CharField(
        source="media_item.title",
        read_only=True,
        allow_null=True,
    )

    management_mode = serializers.CharField(
        source="library.management_mode",
        read_only=True,
    )

    class Meta:
        model = NfoFile

        fields = [
            "id",
            "library",
            "media_item",
            "media_file",
            "media_title",
            "relative_path",
            "file_name",
            "size_bytes",
            "modified_ns",
            "root_element",
            "title",
            "year",
            "raw_xml",
            "parsed_data",
            "parse_status",
            "parse_error",
            "is_generated",
            "is_present",
            "last_seen_at",
            "management_mode",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "library",
            "media_item",
            "media_file",
            "media_title",
            "relative_path",
            "file_name",
            "size_bytes",
            "modified_ns",
            "root_element",
            "title",
            "year",
            "parsed_data",
            "parse_status",
            "parse_error",
            "is_generated",
            "is_present",
            "last_seen_at",
            "management_mode",
            "created_at",
            "updated_at",
        ]
