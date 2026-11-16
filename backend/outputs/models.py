import uuid

from django.conf import settings
from django.db import models


class OutputProfile(models.Model):
    class Target(models.TextChoices):
        JELLYFIN = ("jellyfin", "Jellyfin")
        EMBY = ("emby", "Emby")
        KODI = ("kodi", "Kodi")
        GENERIC = ("generic", "Generic")

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="output_profiles",
    )

    name = models.CharField(
        max_length=255,
    )

    target = models.CharField(
        max_length=32,
        choices=Target.choices,
    )

    nfo_root_element = models.CharField(
        max_length=32,
        default="movie",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["name"]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "owner",
                    "name",
                ],
                name=(
                    "unique_output_profile_"
                    "name_per_owner"
                ),
            )
        ]

    def __str__(self):
        return self.name


class Projection(models.Model):
    class LinkMode(models.TextChoices):
        SYMLINK = (
            "symlink",
            "Symbolic Link",
        )

        HARDLINK = (
            "hardlink",
            "Hardlink",
        )

        COPY = (
            "copy",
            "Copy",
        )

    class Layout(models.TextChoices):
        TEMPLATE = (
            "template",
            "Naming template",
        )

        # Online-video channels as TV shows: hardlinked, renamed videos
        # with tvshow.nfo, episode NFOs, and artwork, kept in sync.
        YOUTUBE_SHOWS = (
            "youtube_shows",
            "Channels as TV shows",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    library = models.ForeignKey(
        "libraries.Library",
        on_delete=models.CASCADE,
        related_name="projections",
    )

    layout = models.CharField(
        max_length=32,
        choices=Layout.choices,
        default=Layout.TEMPLATE,
    )

    output_profile = models.ForeignKey(
        OutputProfile,
        on_delete=models.PROTECT,
        related_name="projections",
    )

    name = models.CharField(
        max_length=255,
    )

    destination_path = models.TextField()

    link_mode = models.CharField(
        max_length=16,
        choices=LinkMode.choices,
    )

    naming_template = models.TextField(
        default=(
            "{channel}/"
            "{date} - {title} "
            "[{youtube_id}]"
        ),
    )

    generate_nfo = models.BooleanField(
        default=True,
    )

    last_run_at = models.DateTimeField(
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
        ordering = ["name"]

    def __str__(self):
        return self.name


class ProjectionItem(models.Model):
    class Status(models.TextChoices):
        CREATED = (
            "created",
            "Created",
        )

        EXISTS = (
            "exists",
            "Already Exists",
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

    projection = models.ForeignKey(
        Projection,
        on_delete=models.CASCADE,
        related_name="items",
    )

    media_file = models.ForeignKey(
        "media.MediaFile",
        on_delete=models.CASCADE,
        related_name="projection_items",
    )

    destination_media_path = models.TextField()

    destination_nfo_path = models.TextField(
        blank=True,
    )

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
    )

    error = models.TextField(
        blank=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "projection",
                    "media_file",
                ],
                name=(
                    "unique_projection_"
                    "media_file"
                ),
            )
        ]


class ProjectionFile(models.Model):
    """One file a projection wrote into its destination folder.

    The manifest is the only list of files a sync may replace or delete:
    anything else in the destination is never touched.
    """

    class Kind(models.TextChoices):
        VIDEO = ("video", "Video link")
        EPISODE_NFO = ("episode_nfo", "Episode NFO")
        THUMB = ("thumb", "Episode thumbnail")
        SHOW_NFO = ("show_nfo", "Show NFO")
        POSTER = ("poster", "Show poster")
        FANART = ("fanart", "Show fanart")

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    projection = models.ForeignKey(
        Projection,
        on_delete=models.CASCADE,
        related_name="files",
    )

    # Relative to the destination, with forward slashes.
    relative_path = models.TextField()

    kind = models.CharField(
        max_length=16,
        choices=Kind.choices,
    )

    media_file = models.ForeignKey(
        "media.MediaFile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projection_files",
    )

    channel = models.ForeignKey(
        "catalog.Channel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projection_files",
    )

    season_number = models.IntegerField(
        null=True,
        blank=True,
    )

    episode_number = models.IntegerField(
        null=True,
        blank=True,
    )

    # Size of the linked source when it was linked, or of the written file.
    size_bytes = models.BigIntegerField(
        null=True,
        blank=True,
    )

    # SHA-256 of a file LibraryForge wrote (blank for video links).
    content_sha256 = models.CharField(
        max_length=64,
        blank=True,
        default="",
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
                    "projection",
                    "relative_path",
                ],
                name="unique_projection_file_path",
            )
        ]

    def __str__(self):
        return self.relative_path
