from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class IntegrationConnection(models.Model):
    class Status(models.TextChoices):
        UNKNOWN = ("unknown", "Unknown")
        CONNECTED = ("connected", "Connected")
        ERROR = ("error", "Error")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="integration_connections",
    )
    name = models.CharField(max_length=255)
    provider = models.CharField(max_length=64, db_index=True)
    enabled = models.BooleanField(default=True, db_index=True)
    configuration = models.JSONField(default=dict, blank=True)
    encrypted_secrets = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.UNKNOWN,
        db_index=True,
    )
    last_tested_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["provider", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "name"],
                name="unique_integration_connection_name_per_owner",
            )
        ]

    def __str__(self):
        return f"{self.provider}: {self.name}"


class LibraryIntegration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    library = models.ForeignKey(
        "libraries.Library",
        on_delete=models.CASCADE,
        related_name="integration_links",
    )
    connection = models.ForeignKey(
        IntegrationConnection,
        on_delete=models.CASCADE,
        related_name="library_links",
    )
    enabled = models.BooleanField(default=True, db_index=True)
    priority = models.PositiveIntegerField(default=100)
    capabilities = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["priority", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["library", "connection"],
                name="unique_library_integration_connection",
            )
        ]

    def __str__(self):
        return f"{self.library} -> {self.connection}"
