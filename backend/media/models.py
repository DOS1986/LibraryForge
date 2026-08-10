import uuid

from django.db import models
from django.db.models import Q


class MediaItem(models.Model):
    class MediaType(models.TextChoices):
        UNKNOWN = (
            "unknown",
            "Unknown",
        )

        MOVIE = (
            "movie",
            "Movie",
        )

        TV_EPISODE = (
            "tv_episode",
            "TV Episode",
        )

        ONLINE_VIDEO = (
            "online_video",
            "Online Video",
        )

        HOME_VIDEO = (
            "home_video",
            "Home Video",
        )

        LECTURE = (
            "lecture",
            "Lecture",
        )

        PODCAST_VIDEO = (
            "podcast_video",
            "Podcast Video",
        )

        RECORDING = (
            "recording",
            "Recording",
        )

        MUSIC_VIDEO = (
            "music_video",
            "Music Video",
        )

        OTHER = (
            "other",
            "Other",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    library = models.ForeignKey(
        "libraries.Library",
        on_delete=models.CASCADE,
        related_name="media_items",
    )

    title = models.CharField(
        max_length=1024,
        db_index=True,
    )

    media_type = models.CharField(
        max_length=32,
        choices=MediaType.choices,
        default=MediaType.UNKNOWN,
        db_index=True,
    )

    semantic_key = models.CharField(
        max_length=1024,
        blank=True,
        db_index=True,
    )

    semantic_locked = models.BooleanField(
        default=False,
    )

    sort_title = models.CharField(
        max_length=1024,
        blank=True,
        default="",
    )

    original_title = models.CharField(
        max_length=1024,
        blank=True,
        default="",
    )

    description = models.TextField(
        blank=True,
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

    release_date = models.DateField(
        null=True,
        blank=True,
    )

    canonical_metadata = models.JSONField(
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
            "title",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "library",
                    "media_type",
                    "semantic_key",
                ],
                condition=~Q(
                    semantic_key=""
                ),
                name=(
                    "unique_library_media_"
                    "semantic_key"
                ),
            )
        ]

    def __str__(self):
        return self.title


class MediaFile(models.Model):
    class ProbeStatus(models.TextChoices):
        PENDING = (
            "pending",
            "Pending",
        )

        OK = (
            "ok",
            "OK",
        )

        ERROR = (
            "error",
            "Error",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    library = models.ForeignKey(
        "libraries.Library",
        on_delete=models.CASCADE,
        related_name="media_files",
    )

    media_item = models.ForeignKey(
        MediaItem,
        on_delete=models.CASCADE,
        related_name="files",
    )

    relative_path = models.TextField()
    file_name = models.TextField()

    extension = models.CharField(
        max_length=32,
        blank=True,
    )

    size_bytes = models.BigIntegerField(
        default=0,
    )

    modified_ns = models.BigIntegerField(
        default=0,
    )

    source_modified_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    duration_seconds = models.FloatField(
        null=True,
        blank=True,
    )

    container_format = models.CharField(
        max_length=255,
        blank=True,
    )

    bit_rate = models.BigIntegerField(
        null=True,
        blank=True,
    )

    video_codec = models.CharField(
        max_length=64,
        blank=True,
    )

    width = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    height = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    frame_rate = models.FloatField(
        null=True,
        blank=True,
    )

    audio_codec = models.CharField(
        max_length=64,
        blank=True,
    )

    audio_channels = (
        models.PositiveSmallIntegerField(
            null=True,
            blank=True,
        )
    )

    probe_status = models.CharField(
        max_length=16,
        choices=ProbeStatus.choices,
        default=ProbeStatus.PENDING,
    )

    probe_error = models.TextField(
        blank=True,
    )

    raw_probe = models.JSONField(
        default=dict,
        blank=True,
    )

    is_present = models.BooleanField(
        default=True,
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
            "relative_path",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "library",
                    "relative_path",
                ],
                name=(
                    "unique_library_"
                    "relative_path"
                ),
            )
        ]

        indexes = [
            models.Index(
                fields=[
                    "library",
                    "is_present",
                ]
            ),
        ]

    def __str__(self):
        return self.relative_path
