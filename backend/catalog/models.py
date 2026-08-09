import uuid

from django.db import models


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

    def __str__(self):
        return (
            f"{self.media_item.title} "
            f"({self.name})"
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
