import uuid

from django.db import models


class MetadataSource(models.Model):
    class SourceType(models.TextChoices):
        FILENAME = ("filename", "Filename")
        FFPROBE = ("ffprobe", "ffprobe")
        EMBEDDED = ("embedded", "Embedded Tags")
        TUBEARCHIVIST = (
            "tubearchivist",
            "TubeArchivist",
        )
        YT_DLP = ("yt_dlp", "yt-dlp")
        NFO = ("nfo", "NFO")

    class Status(models.TextChoices):
        DETECTED = ("detected", "Detected")
        NOT_DETECTED = (
            "not_detected",
            "Not Detected",
        )
        NOT_FOUND = ("not_found", "Not Found")
        ERROR = ("error", "Error")

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    media_item = models.ForeignKey(
        "media.MediaItem",
        on_delete=models.CASCADE,
        related_name="metadata_sources",
    )

    media_file = models.ForeignKey(
        "media.MediaFile",
        on_delete=models.CASCADE,
        related_name="metadata_sources",
    )

    source_type = models.CharField(
        max_length=32,
        choices=SourceType.choices,
    )

    status = models.CharField(
        max_length=32,
        choices=Status.choices,
    )

    extracted_data = models.JSONField(
        default=dict,
        blank=True,
    )

    raw_data = models.JSONField(
        default=dict,
        blank=True,
    )

    error = models.TextField(blank=True)

    first_seen_at = models.DateTimeField(
        auto_now_add=True,
    )

    last_checked_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["source_type"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "media_file",
                    "source_type",
                ],
                name=(
                    "unique_metadata_source_"
                    "per_media_file"
                ),
            )
        ]

    def __str__(self):
        return (
            f"{self.get_source_type_display()}: "
            f"{self.media_file.relative_path}"
        )


class NfoFile(models.Model):
    class ParseStatus(models.TextChoices):
        OK = ("ok", "OK")
        ERROR = ("error", "Error")
        UNPARSED = ("unparsed", "Unparsed")

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    library = models.ForeignKey(
        "libraries.Library",
        on_delete=models.CASCADE,
        related_name="nfo_files",
    )

    media_item = models.ForeignKey(
        "media.MediaItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="nfo_files",
    )

    media_file = models.ForeignKey(
        "media.MediaFile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="nfo_files",
    )

    relative_path = models.TextField()
    file_name = models.TextField()

    size_bytes = models.BigIntegerField(default=0)
    modified_ns = models.BigIntegerField(default=0)

    root_element = models.CharField(
        max_length=64,
        blank=True,
    )

    title = models.TextField(blank=True)

    year = models.IntegerField(
        null=True,
        blank=True,
    )

    raw_xml = models.TextField(blank=True)

    parsed_data = models.JSONField(
        default=dict,
        blank=True,
    )

    parse_status = models.CharField(
        max_length=16,
        choices=ParseStatus.choices,
        default=ParseStatus.UNPARSED,
    )

    parse_error = models.TextField(blank=True)

    is_generated = models.BooleanField(default=False)
    is_present = models.BooleanField(default=True)

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
        ordering = ["relative_path"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "library",
                    "relative_path",
                ],
                name=(
                    "unique_library_"
                    "nfo_relative_path"
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
