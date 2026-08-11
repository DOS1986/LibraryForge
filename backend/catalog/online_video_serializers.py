from rest_framework import serializers

from catalog.models import (
    Channel,
    OnlineVideo,
    Playlist,
    PlaylistMembership,
)


def _artwork_url(obj):
    artwork_id = getattr(obj, "artwork_id", None)
    if not artwork_id:
        return None

    return f"/api/artwork-files/{artwork_id}/content/"


class OnlineVideoVersionSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    edition = serializers.CharField(read_only=True)
    is_primary = serializers.BooleanField(read_only=True)
    file_id = serializers.UUIDField(source="media_file.id", read_only=True)
    file_name = serializers.CharField(source="media_file.file_name", read_only=True)
    relative_path = serializers.CharField(
        source="media_file.relative_path",
        read_only=True,
    )
    size_bytes = serializers.IntegerField(source="media_file.size_bytes", read_only=True)
    duration_seconds = serializers.FloatField(
        source="media_file.duration_seconds",
        read_only=True,
        allow_null=True,
    )
    video_codec = serializers.CharField(source="media_file.video_codec", read_only=True)
    width = serializers.IntegerField(source="media_file.width", read_only=True, allow_null=True)
    height = serializers.IntegerField(source="media_file.height", read_only=True, allow_null=True)


class PlaylistSummarySerializer(serializers.ModelSerializer):
    channel_id = serializers.UUIDField(source="channel.id", read_only=True, allow_null=True)
    channel_title = serializers.CharField(
        source="channel.title",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Playlist
        fields = [
            "id",
            "channel_id",
            "channel_title",
            "provider",
            "source_id",
            "semantic_key",
            "title",
            "source_url",
            "playlist_kind",
        ]


class PlaylistMembershipSummarySerializer(serializers.ModelSerializer):
    playlist = PlaylistSummarySerializer(read_only=True)

    class Meta:
        model = PlaylistMembership
        fields = [
            "id",
            "position",
            "playlist",
        ]


class ChannelCatalogSerializer(serializers.ModelSerializer):
    video_count = serializers.IntegerField(read_only=True)
    runtime_seconds = serializers.FloatField(read_only=True)
    storage_bytes = serializers.IntegerField(read_only=True)
    last_upload_date = serializers.DateField(read_only=True, allow_null=True)
    artwork_url = serializers.SerializerMethodField()

    def get_artwork_url(self, obj):
        return _artwork_url(obj)

    class Meta:
        model = Channel
        fields = [
            "id",
            "library",
            "provider",
            "source_id",
            "semantic_key",
            "title",
            "sort_title",
            "handle",
            "description",
            "source_url",
            "external_ids",
            "canonical_metadata",
            "locked",
            "video_count",
            "runtime_seconds",
            "storage_bytes",
            "last_upload_date",
            "artwork_url",
            "created_at",
            "updated_at",
        ]


class PlaylistCatalogSerializer(serializers.ModelSerializer):
    artwork_url = serializers.SerializerMethodField()
    channel_id = serializers.UUIDField(source="channel.id", read_only=True, allow_null=True)
    channel_title = serializers.CharField(
        source="channel.title",
        read_only=True,
        allow_null=True,
    )
    video_count = serializers.IntegerField(read_only=True)
    runtime_seconds = serializers.FloatField(read_only=True)
    storage_bytes = serializers.IntegerField(read_only=True)

    def get_artwork_url(self, obj):
        return _artwork_url(obj)

    class Meta:
        model = Playlist
        fields = [
            "id",
            "library",
            "channel_id",
            "channel_title",
            "provider",
            "source_id",
            "semantic_key",
            "title",
            "description",
            "source_url",
            "playlist_kind",
            "external_ids",
            "canonical_metadata",
            "locked",
            "artwork_url",
            "video_count",
            "runtime_seconds",
            "storage_bytes",
            "created_at",
            "updated_at",
        ]


class OnlineVideoCatalogSerializer(serializers.ModelSerializer):
    artwork_url = serializers.SerializerMethodField()
    media_item_id = serializers.UUIDField(source="media_item.id", read_only=True)
    title = serializers.CharField(source="media_item.title", read_only=True)
    description = serializers.CharField(source="media_item.description", read_only=True)
    release_date = serializers.DateField(
        source="media_item.release_date",
        read_only=True,
        allow_null=True,
    )
    semantic_key = serializers.CharField(source="media_item.semantic_key", read_only=True)

    channel_id = serializers.UUIDField(source="channel.id", read_only=True, allow_null=True)
    channel_title = serializers.CharField(
        source="channel.title",
        read_only=True,
        allow_null=True,
    )
    channel_handle = serializers.CharField(
        source="channel.handle",
        read_only=True,
        allow_null=True,
    )

    runtime_seconds = serializers.FloatField(read_only=True, allow_null=True)
    storage_bytes = serializers.IntegerField(read_only=True)
    version_count = serializers.IntegerField(read_only=True)
    playlist_count = serializers.IntegerField(read_only=True)

    versions = serializers.SerializerMethodField()
    playlists = serializers.SerializerMethodField()

    def get_artwork_url(self, obj):
        return _artwork_url(obj)

    def get_versions(self, obj):
        versions = getattr(obj.media_item, "present_versions", None)
        if versions is None:
            versions = (
                obj.media_item.versions
                .filter(media_file__is_present=True)
                .select_related("media_file")
                .order_by("-is_primary", "created_at")
            )

        return OnlineVideoVersionSerializer(versions, many=True).data

    def get_playlists(self, obj):
        memberships = getattr(obj, "catalog_playlist_memberships", None)
        if memberships is None:
            memberships = (
                obj.playlist_memberships
                .select_related("playlist", "playlist__channel")
                .order_by("playlist__title", "position")
            )

        return PlaylistMembershipSummarySerializer(memberships, many=True).data

    class Meta:
        model = OnlineVideo
        fields = [
            "id",
            "library",
            "media_item_id",
            "title",
            "description",
            "release_date",
            "semantic_key",
            "channel_id",
            "channel_title",
            "channel_handle",
            "provider",
            "source_id",
            "source_url",
            "upload_date",
            "video_kind",
            "tags",
            "categories",
            "external_ids",
            "canonical_metadata",
            "locked",
            "artwork_url",
            "runtime_seconds",
            "storage_bytes",
            "version_count",
            "playlist_count",
            "versions",
            "playlists",
            "created_at",
            "updated_at",
        ]
