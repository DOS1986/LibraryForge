from django.db.models import Sum

from rest_framework import serializers

from catalog.models import (
    Episode,
    MediaVersion,
    OnlineVideo,
    Season,
    SemanticMatch,
    Series,
)

from media.models import MediaItem


class MediaVersionSerializer(
    serializers.ModelSerializer
):
    file_id = serializers.UUIDField(
        source="media_file.id",
        read_only=True,
    )

    file_name = serializers.CharField(
        source=(
            "media_file.file_name"
        ),
        read_only=True,
    )

    relative_path = serializers.CharField(
        source=(
            "media_file.relative_path"
        ),
        read_only=True,
    )

    size_bytes = serializers.IntegerField(
        source=(
            "media_file.size_bytes"
        ),
        read_only=True,
    )

    duration_seconds = serializers.FloatField(
        source=(
            "media_file.duration_seconds"
        ),
        read_only=True,
        allow_null=True,
    )

    video_codec = serializers.CharField(
        source=(
            "media_file.video_codec"
        ),
        read_only=True,
    )

    width = serializers.IntegerField(
        source="media_file.width",
        read_only=True,
        allow_null=True,
    )

    height = serializers.IntegerField(
        source="media_file.height",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = MediaVersion

        fields = [
            "id",
            "name",
            "edition",
            "is_primary",
            "file_id",
            "file_name",
            "relative_path",
            "size_bytes",
            "duration_seconds",
            "video_codec",
            "width",
            "height",
        ]


class MovieCatalogSerializer(
    serializers.ModelSerializer
):
    year = serializers.SerializerMethodField()
    runtime_seconds = serializers.SerializerMethodField()
    storage_bytes = serializers.SerializerMethodField()
    version_count = serializers.SerializerMethodField()

    versions = serializers.SerializerMethodField()

    def get_year(
        self,
        obj,
    ):
        return (
            obj.canonical_metadata
            .get(
                "semantic",
                {},
            )
            .get(
                "year"
            )
        )

    def get_runtime_seconds(
        self,
        obj,
    ):
        primary = (
            obj.versions
            .filter(
                is_primary=True,
                media_file__is_present=True,
            )
            .select_related(
                "media_file"
            )
            .first()
        )

        if not primary:
            primary = (
                obj.versions
                .filter(
                    media_file__is_present=True
                )
                .select_related(
                    "media_file"
                )
                .first()
            )

        return (
            primary
            .media_file
            .duration_seconds
            if primary
            else None
        )

    def get_storage_bytes(
        self,
        obj,
    ):
        return (
            obj.versions
            .filter(
                media_file__is_present=True
            )
            .aggregate(
                total=Sum(
                    "media_file__size_bytes"
                )
            )
            .get(
                "total"
            )
            or 0
        )

    def get_version_count(
        self,
        obj,
    ):
        return (
            obj.versions
            .filter(
                media_file__is_present=True
            )
            .count()
        )


    def get_versions(
        self,
        obj,
    ):
        versions = (
            obj.versions
            .filter(
                media_file__is_present=True
            )
            .select_related(
                "media_file"
            )
        )

        return (
            MediaVersionSerializer(
                versions,
                many=True,
            )
            .data
        )

    class Meta:
        model = MediaItem

        fields = [
            "id",
            "title",
            "year",
            "runtime_seconds",
            "storage_bytes",
            "version_count",
            "versions",
            "canonical_metadata",
        ]


class SeriesCatalogSerializer(
    serializers.ModelSerializer
):
    season_count = serializers.SerializerMethodField()
    episode_count = serializers.SerializerMethodField()
    runtime_seconds = serializers.SerializerMethodField()
    storage_bytes = serializers.SerializerMethodField()

    def get_season_count(
        self,
        obj,
    ):
        return (
            obj.seasons
            .filter(
                episodes__media_item__versions__media_file__is_present=True
            )
            .distinct()
            .count()
        )

    def get_episode_count(
        self,
        obj,
    ):
        return (
            Episode.objects
            .filter(
                season__series=obj,
                media_item__versions__media_file__is_present=True,
            )
            .distinct()
            .count()
        )

    def get_runtime_seconds(
        self,
        obj,
    ):
        return (
            MediaVersion.objects
            .filter(
                media_item__episode__season__series=(
                    obj
                ),
                is_primary=True,
                media_file__is_present=True,
            )
            .aggregate(
                total=Sum(
                    "media_file__duration_seconds"
                )
            )
            .get(
                "total"
            )
            or 0
        )

    def get_storage_bytes(
        self,
        obj,
    ):
        return (
            MediaVersion.objects
            .filter(
                media_item__episode__season__series=(
                    obj
                ),
                media_file__is_present=True,
            )
            .aggregate(
                total=Sum(
                    "media_file__size_bytes"
                )
            )
            .get(
                "total"
            )
            or 0
        )

    class Meta:
        model = Series

        fields = [
            "id",
            "library",
            "title",
            "sort_title",
            "start_year",
            "end_year",
            "description",
            "season_count",
            "episode_count",
            "runtime_seconds",
            "storage_bytes",
            "canonical_metadata",
            "locked",
        ]


class SeasonCatalogSerializer(
    serializers.ModelSerializer
):
    series_id = serializers.UUIDField(
        source="series.id",
        read_only=True,
    )

    series_title = serializers.CharField(
        source="series.title",
        read_only=True,
    )

    episode_count = serializers.SerializerMethodField()
    runtime_seconds = serializers.SerializerMethodField()
    storage_bytes = serializers.SerializerMethodField()

    def get_episode_count(
        self,
        obj,
    ):
        return (
            obj.episodes
            .filter(
                media_item__versions__media_file__is_present=True
            )
            .distinct()
            .count()
        )

    def get_runtime_seconds(
        self,
        obj,
    ):
        return (
            MediaVersion.objects
            .filter(
                media_item__episode__season=obj,
                is_primary=True,
                media_file__is_present=True,
            )
            .aggregate(
                total=Sum(
                    "media_file__duration_seconds"
                )
            )
            .get(
                "total"
            )
            or 0
        )

    def get_storage_bytes(
        self,
        obj,
    ):
        return (
            MediaVersion.objects
            .filter(
                media_item__episode__season=obj,
                media_file__is_present=True,
            )
            .aggregate(
                total=Sum(
                    "media_file__size_bytes"
                )
            )
            .get(
                "total"
            )
            or 0
        )

    class Meta:
        model = Season

        fields = [
            "id",
            "series_id",
            "series_title",
            "season_number",
            "title",
            "description",
            "episode_count",
            "runtime_seconds",
            "storage_bytes",
            "canonical_metadata",
            "locked",
        ]


class EpisodeCatalogSerializer(
    serializers.ModelSerializer
):
    media_item_id = serializers.UUIDField(
        source="media_item.id",
        read_only=True,
    )

    title = serializers.CharField(
        source="media_item.title",
        read_only=True,
    )

    series_id = serializers.UUIDField(
        source="season.series.id",
        read_only=True,
    )

    series_title = serializers.CharField(
        source="season.series.title",
        read_only=True,
    )

    season_number = serializers.IntegerField(
        source="season.season_number",
        read_only=True,
    )

    runtime_seconds = serializers.SerializerMethodField()
    storage_bytes = serializers.SerializerMethodField()
    version_count = serializers.SerializerMethodField()

    versions = serializers.SerializerMethodField()

    def _versions(
        self,
        obj,
    ):
        return (
            obj.media_item
            .versions
            .filter(
                media_file__is_present=True
            )
            .select_related(
                "media_file"
            )
        )

    def get_runtime_seconds(
        self,
        obj,
    ):
        versions = self._versions(
            obj
        )

        primary = (
            versions
            .filter(
                is_primary=True
            )
            .first()
            or versions.first()
        )

        return (
            primary
            .media_file
            .duration_seconds
            if primary
            else None
        )

    def get_storage_bytes(
        self,
        obj,
    ):
        return (
            self._versions(
                obj
            )
            .aggregate(
                total=Sum(
                    "media_file__size_bytes"
                )
            )
            .get(
                "total"
            )
            or 0
        )

    def get_version_count(
        self,
        obj,
    ):
        return (
            self._versions(
                obj
            )
            .count()
        )

    def get_versions(
        self,
        obj,
    ):
        return (
            MediaVersionSerializer(
                self._versions(
                    obj
                ),
                many=True,
            )
            .data
        )

    class Meta:
        model = Episode

        fields = [
            "id",
            "media_item_id",
            "series_id",
            "series_title",
            "season",
            "season_number",
            "episode_number",
            "episode_end_number",
            "absolute_number",
            "title",
            "air_date",
            "runtime_seconds",
            "storage_bytes",
            "version_count",
            "versions",
            "locked",
        ]


class SemanticMatchSerializer(
    serializers.ModelSerializer
):
    library_id = serializers.UUIDField(
        source="media_file.library_id",
        read_only=True,
    )

    library_name = serializers.CharField(
        source="media_file.library.name",
        read_only=True,
    )

    file_name = serializers.CharField(
        source="media_file.file_name",
        read_only=True,
    )

    relative_path = serializers.CharField(
        source=(
            "media_file.relative_path"
        ),
        read_only=True,
    )

    size_bytes = serializers.IntegerField(
        source="media_file.size_bytes",
        read_only=True,
    )

    duration_seconds = serializers.FloatField(
        source=(
            "media_file.duration_seconds"
        ),
        read_only=True,
        allow_null=True,
    )

    video_codec = serializers.CharField(
        source="media_file.video_codec",
        read_only=True,
    )

    width = serializers.IntegerField(
        source="media_file.width",
        read_only=True,
        allow_null=True,
    )

    height = serializers.IntegerField(
        source="media_file.height",
        read_only=True,
        allow_null=True,
    )

    media_item_id = serializers.UUIDField(
        source="media_file.media_item_id",
        read_only=True,
    )

    media_title = serializers.CharField(
        source=(
            "media_file.media_item.title"
        ),
        read_only=True,
    )

    current_assignment = (
        serializers.SerializerMethodField()
    )

    status_label = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    source_label = serializers.CharField(
        source="get_source_display",
        read_only=True,
    )

    def get_current_assignment(
        self,
        obj,
    ):
        media_item = (
            obj.media_file
            .media_item
        )

        if (
            media_item.media_type
            == MediaItem.MediaType.ONLINE_VIDEO
        ):
            try:
                online_video = media_item.online_video
            except OnlineVideo.DoesNotExist:
                online_video = None

            if online_video:
                return {
                    "kind": "online_video",
                    "media_item_id": str(media_item.id),
                    "title": media_item.title,
                    "provider": online_video.provider,
                    "source_id": online_video.source_id,
                    "semantic_key": media_item.semantic_key,
                    "channel_id": (
                        online_video.channel.source_id
                        if online_video.channel_id
                        else ""
                    ),
                    "channel_title": (
                        online_video.channel.title
                        if online_video.channel_id
                        else ""
                    ),
                    "channel_handle": (
                        online_video.channel.handle
                        if online_video.channel_id
                        else ""
                    ),
                }

        if (
            media_item.media_type
            == MediaItem
            .MediaType
            .MOVIE
            and media_item.semantic_key
        ):
            return {
                "kind":
                    "movie",

                "media_item_id":
                    str(
                        media_item.id
                    ),

                "title":
                    media_item.title,

                "year":
                    (
                        media_item
                        .canonical_metadata
                        .get(
                            "semantic",
                            {},
                        )
                        .get(
                            "year"
                        )
                    ),
            }

        try:
            episode = (
                media_item.episode
            )

        except Episode.DoesNotExist:
            episode = None

        if episode:
            return {
                "kind":
                    "episode",

                "media_item_id":
                    str(
                        media_item.id
                    ),

                "title":
                    media_item.title,

                "series_id":
                    str(
                        episode
                        .season
                        .series_id
                    ),

                "series_title":
                    episode
                    .season
                    .series
                    .title,

                "season_id":
                    str(
                        episode
                        .season_id
                    ),

                "season_number":
                    episode
                    .season
                    .season_number,

                "episode_number":
                    episode
                    .episode_number,

                "episode_end_number":
                    episode
                    .episode_end_number,
            }

        return None

    class Meta:
        model = SemanticMatch

        fields = [
            "id",
            "library_id",
            "library_name",
            "media_item_id",
            "media_title",
            "current_assignment",
            "file_name",
            "relative_path",
            "size_bytes",
            "duration_seconds",
            "video_codec",
            "width",
            "height",
            "status",
            "status_label",
            "source",
            "source_label",
            "confidence",
            "candidate_data",
            "locked",
            "notes",
            "last_resolved_at",
            "created_at",
            "updated_at",
        ]


class SemanticResolveRequestSerializer(
    serializers.Serializer
):
    candidate_source = (
        serializers.ChoiceField(
            choices=[
                "nfo",
                "filename",
                "suggested",
                "tubearchivist",
                "yt_dlp",
                "tubearchivist_path",
                "manual",
            ]
        )
    )

    lock = serializers.BooleanField(
        default=True,
    )

    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )

    kind = serializers.ChoiceField(
        choices=[
            "movie",
            "episode",
            "online_video",
        ],
        required=False,
    )

    title = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=1024,
    )

    year = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1800,
        max_value=3000,
    )

    edition = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=255,
    )

    series_title = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=1024,
    )

    series_year = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1800,
        max_value=3000,
    )

    season_number = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=0,
        max_value=9999,
    )

    episode_number = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        max_value=99999,
    )

    episode_end_number = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        max_value=99999,
    )

    episode_title = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=1024,
    )

    provider = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=64,
    )

    video_id = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=255,
    )

    channel_id = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=255,
    )

    channel_title = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=1024,
    )

    channel_handle = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=255,
    )

    source_url = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )

    upload_date = serializers.DateField(
        required=False,
        allow_null=True,
    )

    video_kind = serializers.ChoiceField(
        choices=OnlineVideo.VideoKind.choices,
        required=False,
        default=OnlineVideo.VideoKind.UNKNOWN,
    )

    def validate(
        self,
        attrs,
    ):
        if (
            attrs[
                "candidate_source"
            ]
            != "manual"
        ):
            return attrs

        kind = attrs.get(
            "kind"
        )

        if kind == "movie":
            if not (
                attrs.get(
                    "title",
                    "",
                )
                .strip()
            ):
                raise serializers.ValidationError(
                    {
                        "title":
                            (
                                "Movie title "
                                "is required."
                            )
                    }
                )

            return attrs

        if kind == "online_video":
            errors = {}

            if not attrs.get("provider", "").strip():
                errors["provider"] = "Provider is required."

            if not attrs.get("video_id", "").strip():
                errors["video_id"] = "Video/source ID is required."

            if errors:
                raise serializers.ValidationError(errors)

            return attrs

        if kind == "episode":
            errors = {}

            if not (
                attrs.get(
                    "series_title",
                    "",
                )
                .strip()
            ):
                errors[
                    "series_title"
                ] = (
                    "Series title is required."
                )

            if (
                attrs.get(
                    "season_number"
                )
                is None
            ):
                errors[
                    "season_number"
                ] = (
                    "Season number is required."
                )

            if (
                attrs.get(
                    "episode_number"
                )
                is None
            ):
                errors[
                    "episode_number"
                ] = (
                    "Episode number is required."
                )

            if errors:
                raise serializers.ValidationError(
                    errors
                )

            return attrs

        raise serializers.ValidationError(
            {
                "kind":
                    (
                        "Choose Movie, TV Episode, "
                        "or Online Video."
                    )
            }
        )


class SemanticLockRequestSerializer(
    serializers.Serializer
):
    locked = serializers.BooleanField()

