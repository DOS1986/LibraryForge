import uuid

from django.conf import settings
from django.db import models


class Library(models.Model):
    class ManagementMode(models.TextChoices):
        FULL_CONTROL = (
            "full_control",
            "Full Control",
        )

        SIDECAR_ONLY = (
            "sidecar_only",
            "Sidecar Only",
        )

        READ_ONLY = (
            "read_only",
            "Read Only",
        )

    class ContentType(models.TextChoices):
        AUTO = (
            "auto",
            "Automatic",
        )

        MOVIES = (
            "movies",
            "Movies",
        )

        TV = (
            "tv",
            "TV Shows",
        )

        ONLINE_VIDEO = (
            "online_video",
            "Online Video",
        )

        MIXED = (
            "mixed",
            "Mixed Media",
        )

        GENERIC = (
            "generic",
            "Generic Video",
        )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="libraries",
    )

    name = models.CharField(
        max_length=255,
    )

    path = models.TextField()

    management_mode = models.CharField(
        max_length=32,
        choices=ManagementMode.choices,
        default=ManagementMode.READ_ONLY,
    )

    content_type = models.CharField(
        max_length=32,
        choices=ContentType.choices,
        default=ContentType.AUTO,
        db_index=True,
    )

    last_scanned_at = models.DateTimeField(
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
            "name",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "owner",
                    "path",
                ],
                name=(
                    "unique_library_"
                    "owner_path"
                ),
            )
        ]

    def __str__(self):
        return self.name
