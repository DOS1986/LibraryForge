from django.conf import settings
from django.db import models


class UserSettings(models.Model):
    class PageSize(models.IntegerChoices):
        TEN = 10, "10"
        TWENTY = 20, "20"
        FIFTY = 50, "50"
        ONE_HUNDRED = 100, "100"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="libraryforge_settings",
    )

    display_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
    )

    default_page_size = models.PositiveSmallIntegerField(
        choices=PageSize.choices,
        default=PageSize.TWENTY,
    )

    needs_attention_unresolved_sort = models.CharField(
        max_length=100,
        default="confidence",
    )

    needs_attention_conflict_sort = models.CharField(
        max_length=100,
        default="-updated_at",
    )

    needs_attention_confirmed_sort = models.CharField(
        max_length=100,
        default="-updated_at",
    )

    show_build_information = models.BooleanField(
        default=True,
    )

    confirm_restart = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        verbose_name = "user settings"
        verbose_name_plural = "user settings"

    def __str__(self):
        return f"Settings for {self.user}"


class SystemAction(models.Model):
    class Action(models.TextChoices):
        RESTART = "restart", "Restart"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="libraryforge_system_actions",
    )

    action = models.CharField(
        max_length=32,
        choices=Action.choices,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_action_display()} at {self.created_at}"
