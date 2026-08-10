from rest_framework import serializers

from metadata.serializers import (
    MetadataSourceSerializer,
)

from .models import (
    MediaFile,
    MediaItem,
)


class LibraryAssetSerializer(
    serializers.Serializer
):
    id = serializers.UUIDField()

    library = serializers.UUIDField()

    media_item = serializers.UUIDField(
        allow_null=True,
    )

    media_title = serializers.CharField(
        allow_null=True,
        allow_blank=True,
    )

    asset_type = serializers.ChoiceField(
        choices=[
            "media",
            "nfo",
            "artwork",
        ]
    )

    relative_path = serializers.CharField()

    file_name = serializers.CharField()

    size_bytes = serializers.IntegerField()

    is_present = serializers.BooleanField()

    metadata_status = serializers.CharField()


class MediaFileSerializer(
    serializers.ModelSerializer
):
    title = serializers.CharField(
        source="media_item.title",
        read_only=True,
    )

    media_type = serializers.CharField(
        source="media_item.media_type",
        read_only=True,
    )

    class Meta:
        model = MediaFile

        fields = [
            "id",
            "library",
            "media_item",
            "title",
            "media_type",
            "relative_path",
            "file_name",
            "extension",
            "size_bytes",
            "source_modified_at",
            "duration_seconds",
            "container_format",
            "bit_rate",
            "video_codec",
            "width",
            "height",
            "frame_rate",
            "audio_codec",
            "audio_channels",
            "probe_status",
            "probe_error",
            "is_present",
            "last_seen_at",
        ]

        read_only_fields = fields


class MediaItemDetailSerializer(
    serializers.ModelSerializer
):
    files = MediaFileSerializer(
        many=True,
        read_only=True,
    )

    metadata_sources = MetadataSourceSerializer(
        many=True,
        read_only=True,
    )

    media_type_label = serializers.CharField(
        source="get_media_type_display",
        read_only=True,
    )

    tags = serializers.SerializerMethodField()

    def get_tags(
        self,
        obj,
    ):
        return (
            obj.canonical_metadata
            .get(
                "tags",
                [],
            )
        )

    class Meta:
        model = MediaItem

        fields = [
            "id",
            "library",
            "title",
            "media_type",
            "media_type_label",
            "description",
            "release_date",
            "tags",
            "canonical_metadata",
            "files",
            "metadata_sources",
            "created_at",
            "updated_at",
        ]
