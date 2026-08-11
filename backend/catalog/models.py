import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Series(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    library = models.ForeignKey(
        "libraries.Library",
        on_delete=models.CASCADE,
        related_name="series",
    )

    title = models.CharField(
        max_length=1024,
    )

    sort_title = models.CharField(
        max_length=1024,
        blank=True,
    )

    original_title = models.CharField(
        max_length=1024,
        blank=True,
        default="",
    )

    tagline = models.TextField(
        blank=True,
        default="",
    )

    content_rating = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )

    genres = models.JSONField(
        default=list,
        blank=True,
    )

    studios = models.JSONField(
        default=list,
        blank=True,
    )

    external_ids = models.JSONField(
        default=dict,
        blank=True,
    )

    semantic_key = models.CharField(
        max_length=1024,
    )

    start_year = models.IntegerField(
        null=True,
        blank=True,
    )

    end_year = models.IntegerField(
        null=True,
        blank=True,
    )

    description = models.TextField(
        blank=True,
    )

    canonical_metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    locked = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "sort_title",
            "title",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "library",
                    "semantic_key",
                ],
                name=(
                    "unique_library_"
                    "series_semantic_key"
                ),
            )
        ]

    def __str__(self):
        return self.title


class Season(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    series = models.ForeignKey(
        Series,
        on_delete=models.CASCADE,
        related_name="seasons",
    )

    season_number = models.IntegerField()

    title = models.CharField(
        max_length=1024,
        blank=True,
    )

    description = models.TextField(
        blank=True,
    )

    canonical_metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    external_ids = models.JSONField(
        default=dict,
        blank=True,
    )

    locked = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "season_number",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "series",
                    "season_number",
                ],
                name=(
                    "unique_series_"
                    "season_number"
                ),
            )
        ]

    def __str__(self):
        if self.season_number == 0:
            return (
                f"{self.series.title} - "
                "Specials"
            )

        return (
            f"{self.series.title} - "
            f"Season {self.season_number}"
        )


class Episode(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    media_item = models.OneToOneField(
        "media.MediaItem",
        on_delete=models.CASCADE,
        related_name="episode",
    )

    season = models.ForeignKey(
        Season,
        on_delete=models.CASCADE,
        related_name="episodes",
    )

    episode_number = models.IntegerField()

    episode_end_number = models.IntegerField(
        null=True,
        blank=True,
    )

    absolute_number = models.IntegerField(
        null=True,
        blank=True,
    )

    air_date = models.DateField(
        null=True,
        blank=True,
    )

    external_ids = models.JSONField(
        default=dict,
        blank=True,
    )

    locked = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "episode_number",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "season",
                    "episode_number",
                ],
                name=(
                    "unique_season_"
                    "episode_number"
                ),
            )
        ]

    def __str__(self):
        return (
            f"{self.season.series.title} "
            f"S{self.season.season_number:02d}"
            f"E{self.episode_number:02d}"
        )


class MediaVersion(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    media_item = models.ForeignKey(
        "media.MediaItem",
        on_delete=models.CASCADE,
        related_name="versions",
    )

    media_file = models.OneToOneField(
        "media.MediaFile",
        on_delete=models.CASCADE,
        related_name="semantic_version",
    )

    name = models.CharField(
        max_length=255,
        default="Default",
    )

    edition = models.CharField(
        max_length=255,
        blank=True,
    )

    notes = models.TextField(
        blank=True,
        default="",
    )

    is_primary = models.BooleanField(
        default=False,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "-is_primary",
            "name",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "media_item",
                ],
                condition=Q(
                    is_primary=True
                ),
                name=(
                    "unique_primary_media_version"
                ),
            )
        ]

    def __str__(self):
        return (
            f"{self.media_item.title} "
            f"({self.name})"
        )


class Channel(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    library = models.ForeignKey(
        "libraries.Library",
        on_delete=models.CASCADE,
        related_name="channels",
    )

    provider = models.CharField(
        max_length=64,
        db_index=True,
    )

    source_id = models.CharField(
        max_length=255,
    )

    semantic_key = models.CharField(
        max_length=1024,
        db_index=True,
    )

    title = models.CharField(
        max_length=1024,
    )

    sort_title = models.CharField(
        max_length=1024,
        blank=True,
        default="",
    )

    handle = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    description = models.TextField(
        blank=True,
        default="",
    )

    source_url = models.TextField(
        blank=True,
        default="",
    )

    external_ids = models.JSONField(
        default=dict,
        blank=True,
    )

    canonical_metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    locked = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "sort_title",
            "title",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "library",
                    "provider",
                    "source_id",
                ],
                name="unique_library_channel_source",
            )
        ]

    def __str__(self):
        return self.title


class OnlineVideo(models.Model):
    class VideoKind(models.TextChoices):
        VIDEO = (
            "video",
            "Video",
        )
        SHORT = (
            "short",
            "Short",
        )
        STREAM = (
            "stream",
            "Stream",
        )
        UNKNOWN = (
            "unknown",
            "Unknown",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    library = models.ForeignKey(
        "libraries.Library",
        on_delete=models.CASCADE,
        related_name="online_videos",
    )

    media_item = models.OneToOneField(
        "media.MediaItem",
        on_delete=models.CASCADE,
        related_name="online_video",
    )

    channel = models.ForeignKey(
        Channel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="videos",
    )

    provider = models.CharField(
        max_length=64,
        db_index=True,
    )

    source_id = models.CharField(
        max_length=255,
    )

    source_url = models.TextField(
        blank=True,
        default="",
    )

    upload_date = models.DateField(
        null=True,
        blank=True,
    )

    video_kind = models.CharField(
        max_length=32,
        choices=VideoKind.choices,
        default=VideoKind.UNKNOWN,
        db_index=True,
    )

    tags = models.JSONField(
        default=list,
        blank=True,
    )

    categories = models.JSONField(
        default=list,
        blank=True,
    )

    external_ids = models.JSONField(
        default=dict,
        blank=True,
    )

    canonical_metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    locked = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "-upload_date",
            "source_id",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "library",
                    "provider",
                    "source_id",
                ],
                name="unique_library_online_video_source",
            )
        ]

    def __str__(self):
        return self.media_item.title


class Playlist(models.Model):
    class PlaylistKind(models.TextChoices):
        REMOTE = (
            "remote",
            "Remote",
        )
        CUSTOM = (
            "custom",
            "Custom",
        )
        UNKNOWN = (
            "unknown",
            "Unknown",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    library = models.ForeignKey(
        "libraries.Library",
        on_delete=models.CASCADE,
        related_name="playlists",
    )

    channel = models.ForeignKey(
        Channel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="playlists",
    )

    provider = models.CharField(
        max_length=64,
        db_index=True,
    )

    source_id = models.CharField(
        max_length=255,
    )

    semantic_key = models.CharField(
        max_length=1024,
        db_index=True,
    )

    title = models.CharField(
        max_length=1024,
    )

    description = models.TextField(
        blank=True,
        default="",
    )

    source_url = models.TextField(
        blank=True,
        default="",
    )

    playlist_kind = models.CharField(
        max_length=32,
        choices=PlaylistKind.choices,
        default=PlaylistKind.UNKNOWN,
    )

    external_ids = models.JSONField(
        default=dict,
        blank=True,
    )

    canonical_metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    locked = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "title",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "library",
                    "provider",
                    "source_id",
                ],
                name="unique_library_playlist_source",
            )
        ]

    def __str__(self):
        return self.title


class PlaylistMembership(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    playlist = models.ForeignKey(
        Playlist,
        on_delete=models.CASCADE,
        related_name="memberships",
    )

    online_video = models.ForeignKey(
        OnlineVideo,
        on_delete=models.CASCADE,
        related_name="playlist_memberships",
    )

    position = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "position",
            "created_at",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "playlist",
                    "online_video",
                ],
                name="unique_playlist_online_video",
            )
        ]

    def __str__(self):
        return (
            f"{self.playlist.title}: "
            f"{self.online_video.media_item.title}"
        )


class SemanticMatch(models.Model):
    class Status(models.TextChoices):
        MATCHED = (
            "matched",
            "Matched",
        )

        UNRESOLVED = (
            "unresolved",
            "Unresolved",
        )

        CONFLICT = (
            "conflict",
            "Conflict",
        )

        MANUAL = (
            "manual",
            "Manual",
        )

    class Source(models.TextChoices):
        NFO = (
            "nfo",
            "NFO",
        )

        FILENAME = (
            "filename",
            "Filename",
        )

        FOLDER = (
            "folder",
            "Folder Structure",
        )

        MANUAL = (
            "manual",
            "Manual",
        )

        TUBEARCHIVIST = (
            "tubearchivist",
            "TubeArchivist",
        )

        TUBEARCHIVIST_PATH = (
            "tubearchivist_path",
            "TubeArchivist Path",
        )

        YT_DLP = (
            "yt_dlp",
            "yt-dlp",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    media_file = models.OneToOneField(
        "media.MediaFile",
        on_delete=models.CASCADE,
        related_name="semantic_match",
    )

    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.UNRESOLVED,
        db_index=True,
    )

    source = models.CharField(
        max_length=32,
        choices=Source.choices,
        blank=True,
    )

    confidence = models.FloatField(
        default=0,
    )

    candidate_data = models.JSONField(
        default=dict,
        blank=True,
    )

    locked = models.BooleanField(
        default=False,
    )

    notes = models.TextField(
        blank=True,
    )

    last_resolved_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return (
            f"{self.media_file.relative_path}: "
            f"{self.status}"
        )

class CanonicalFieldState(models.Model):
    class TargetType(models.TextChoices):
        MEDIA_ITEM = (
            "media_item",
            "Media Item",
        )

        SERIES = (
            "series",
            "Series",
        )

        SEASON = (
            "season",
            "Season",
        )

        EPISODE = (
            "episode",
            "Episode",
        )

        MEDIA_VERSION = (
            "media_version",
            "Media Version",
        )

        CHANNEL = (
            "channel",
            "Channel",
        )

        ONLINE_VIDEO = (
            "online_video",
            "Online Video",
        )

        PLAYLIST = (
            "playlist",
            "Playlist",
        )

    class Source(models.TextChoices):
        MANUAL = (
            "manual",
            "Manual",
        )

        NFO = (
            "nfo",
            "NFO",
        )

        FILENAME = (
            "filename",
            "Filename",
        )

        FOLDER = (
            "folder",
            "Folder Structure",
        )

        FFPROBE = (
            "ffprobe",
            "ffprobe",
        )

        EMBEDDED = (
            "embedded",
            "Embedded Tags",
        )

        TUBEARCHIVIST = (
            "tubearchivist",
            "TubeArchivist",
        )

        TUBEARCHIVIST_PATH = (
            "tubearchivist_path",
            "TubeArchivist Path",
        )

        YT_DLP = (
            "yt_dlp",
            "yt-dlp",
        )

        SYSTEM = (
            "system",
            "System",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    target_type = models.CharField(
        max_length=32,
        choices=TargetType.choices,
        db_index=True,
    )

    target_id = models.UUIDField(
        db_index=True,
    )

    field_name = models.CharField(
        max_length=128,
    )

    source = models.CharField(
        max_length=32,
        choices=Source.choices,
        default=Source.SYSTEM,
    )

    source_ref = models.CharField(
        max_length=255,
        blank=True,
    )

    value_snapshot = models.JSONField(
        null=True,
        blank=True,
    )

    locked = models.BooleanField(
        default=False,
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="canonical_field_updates",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "field_name",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "target_type",
                    "target_id",
                    "field_name",
                ],
                name=(
                    "unique_canonical_field_state"
                ),
            )
        ]

        indexes = [
            models.Index(
                fields=[
                    "target_type",
                    "target_id",
                ]
            ),
        ]

    def __str__(self):
        return (
            f"{self.target_type}:"
            f"{self.target_id}:"
            f"{self.field_name}"
        )


class MetadataChangeSet(models.Model):
    class Source(models.TextChoices):
        MANUAL = (
            "manual",
            "Manual",
        )

        SYSTEM = (
            "system",
            "System",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    target_type = models.CharField(
        max_length=32,
        choices=(
            CanonicalFieldState
            .TargetType
            .choices
        ),
        db_index=True,
    )

    target_id = models.UUIDField(
        db_index=True,
    )

    source = models.CharField(
        max_length=32,
        choices=Source.choices,
        default=Source.MANUAL,
    )

    changes = models.JSONField(
        default=dict,
    )

    note = models.TextField(
        blank=True,
    )

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="metadata_change_sets",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        ordering = [
            "-created_at",
        ]

        indexes = [
            models.Index(
                fields=[
                    "target_type",
                    "target_id",
                    "created_at",
                ]
            ),
        ]

    def __str__(self):
        return (
            f"{self.target_type}:"
            f"{self.target_id} "
            f"@ {self.created_at}"
        )


class ArtworkFile(models.Model):
    class TargetType(models.TextChoices):
        MEDIA_ITEM = (
            "media_item",
            "Media Item",
        )
        SERIES = (
            "series",
            "Series",
        )
        SEASON = (
            "season",
            "Season",
        )
        EPISODE = (
            "episode",
            "Episode",
        )
        CHANNEL = (
            "channel",
            "Channel",
        )
        PLAYLIST = (
            "playlist",
            "Playlist",
        )

    class ArtworkType(models.TextChoices):
        PRIMARY = (
            "primary",
            "Primary",
        )
        BACKDROP = (
            "backdrop",
            "Backdrop",
        )
        BANNER = (
            "banner",
            "Banner",
        )
        LOGO = (
            "logo",
            "Logo",
        )
        THUMB = (
            "thumb",
            "Thumb",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    library = models.ForeignKey(
        "libraries.Library",
        on_delete=models.CASCADE,
        related_name="artwork_files",
    )

    target_type = models.CharField(
        max_length=32,
        choices=TargetType.choices,
        db_index=True,
    )

    target_id = models.UUIDField(
        db_index=True,
    )

    artwork_type = models.CharField(
        max_length=32,
        choices=ArtworkType.choices,
        db_index=True,
    )

    source_name = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )

    relative_path = models.TextField()
    file_name = models.TextField()

    extension = models.CharField(
        max_length=16,
        blank=True,
        default="",
    )

    size_bytes = models.BigIntegerField(
        default=0,
    )

    modified_ns = models.BigIntegerField(
        default=0,
    )

    is_selected = models.BooleanField(
        default=False,
        db_index=True,
    )

    is_present = models.BooleanField(
        default=True,
        db_index=True,
    )

    last_seen_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "target_type",
            "target_id",
            "artwork_type",
            "relative_path",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "library",
                    "relative_path",
                ],
                name="unique_library_artwork_path",
            ),
            models.UniqueConstraint(
                fields=[
                    "library",
                    "target_type",
                    "target_id",
                    "artwork_type",
                ],
                condition=Q(
                    is_selected=True,
                    is_present=True,
                ),
                name="unique_selected_target_artwork",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "library",
                    "is_present",
                ]
            ),
            models.Index(
                fields=[
                    "target_type",
                    "target_id",
                    "artwork_type",
                ]
            ),
        ]

    def __str__(self):
        return (
            f"{self.target_type}:{self.target_id} "
            f"{self.artwork_type} - {self.relative_path}"
        )

