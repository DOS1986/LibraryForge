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

    class StalePolicy(models.TextChoices):
        # Remove output LibraryForge created whose source is gone, if unchanged.
        REMOVE_OWNED = ("remove_owned", "Remove owned, unchanged files")
        KEEP = ("keep", "Keep and report")

    layout = models.CharField(
        max_length=32,
        choices=Layout.choices,
        default=Layout.TEMPLATE,
    )

    stale_policy = models.CharField(
        max_length=16,
        choices=StalePolicy.choices,
        default=StalePolicy.REMOVE_OWNED,
    )

    # A hardlink is the same file under a second name; the owner confirms
    # they understand nothing should write into media through the output.
    hardlink_acknowledged = models.BooleanField(
        default=False,
    )

    enabled = models.BooleanField(
        default=True,
    )

    needs_preview = models.BooleanField(
        default=False,
    )

    last_successful_run = models.ForeignKey(
        "ProjectionRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
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

    class Ownership(models.TextChoices):
        OWNED = ("owned", "Owned")
        # Written before run journals existed; verified against disk on first use.
        LEGACY_UNVERIFIED = ("legacy_unverified", "Legacy, not yet verified")
        LEGACY_VERIFIED = ("legacy_verified", "Legacy, verified")

    ownership = models.CharField(
        max_length=24,
        choices=Ownership.choices,
        default=Ownership.OWNED,
    )

    last_run = models.ForeignKey(
        "ProjectionRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
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


class ProjectionPlan(models.Model):
    """A reviewed, stored set of changes for one projection.

    Building a plan reads only. A run applies exactly these actions,
    rechecking each one; a plan whose inputs changed must be rebuilt.
    """

    class Status(models.TextChoices):
        READY = ("ready", "Ready")
        BLOCKED = ("blocked", "Blocked")
        APPLIED = ("applied", "Applied")
        SUPERSEDED = ("superseded", "Superseded")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    projection = models.ForeignKey(Projection, on_delete=models.SET_NULL, null=True, related_name="plans")
    # Kept so history stays readable after the projection is deleted.
    projection_name = models.CharField(max_length=255, blank=True, default="")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.READY)
    # Optional scope: one channel (online video) or other object.
    scope = models.JSONField(default=dict, blank=True)
    content_digest = models.CharField(max_length=64)
    manifest_revision = models.CharField(max_length=64)
    counts = models.JSONField(default=dict, blank=True)
    findings = models.JSONField(default=list, blank=True)
    # Layout-specific summary for the preview (for example channels and folders).
    overview = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]


class ProjectionPlanAction(models.Model):
    class Action(models.TextChoices):
        CREATE = ("create", "Create")
        UPDATE = ("update", "Update")
        RELINK = ("relink", "Relink")
        REPLACE = ("replace", "Replace")
        DELETE = ("delete", "Remove")
        ARTWORK = ("artwork", "Fetch artwork")
        RETAIN = ("retain", "Keep")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(ProjectionPlan, on_delete=models.CASCADE, related_name="actions")
    ordinal = models.PositiveIntegerField()
    action = models.CharField(max_length=16, choices=Action.choices)
    kind = models.CharField(max_length=16)
    relative_path = models.TextField()
    comparison_key = models.TextField()
    channel = models.ForeignKey("catalog.Channel", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    media_file = models.ForeignKey("media.MediaFile", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    manifest_file = models.ForeignKey(ProjectionFile, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    # What the target looked like when planned (manifest size/hash) and what it should become.
    expected = models.JSONField(default=dict, blank=True)
    desired = models.JSONField(default=dict, blank=True)
    # Generated file contents (NFOs), stored so a run never re-renders.
    content = models.TextField(blank=True, default="")
    content_sha256 = models.CharField(max_length=64, blank=True, default="")
    reason = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["plan", "ordinal"]
        constraints = [
            models.UniqueConstraint(fields=["plan", "ordinal"], name="unique_plan_action_ordinal"),
        ]


class ProjectionRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = ("queued", "Queued")
        RUNNING = ("running", "Running")
        SUCCEEDED = ("succeeded", "Succeeded")
        COMPLETED_WITH_ERRORS = ("completed_with_errors", "Completed with errors")
        FAILED = ("failed", "Failed")
        CANCELLED = ("cancelled", "Cancelled")
        INTERRUPTED = ("interrupted", "Interrupted")

    ACTIVE = (Status.QUEUED, Status.RUNNING)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(ProjectionPlan, on_delete=models.SET_NULL, null=True, related_name="runs")
    projection = models.ForeignKey(Projection, on_delete=models.SET_NULL, null=True, related_name="runs")
    projection_name = models.CharField(max_length=255, blank=True, default="")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    idempotency_key = models.CharField(max_length=64)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.QUEUED)
    worker_id = models.CharField(max_length=64, blank=True, default="")
    cancel_requested = models.BooleanField(default=False)
    total = models.PositiveIntegerField(default=0)
    done = models.PositiveIntegerField(default=0)
    counts = models.JSONField(default=dict, blank=True)
    problems = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["projection", "idempotency_key"], name="unique_projection_run_idempotency_key"
            ),
            models.UniqueConstraint(
                fields=["projection"],
                condition=models.Q(status__in=["queued", "running"]),
                name="one_active_run_per_projection",
            ),
        ]


class ProjectionRunAction(models.Model):
    """The run journal: intent is recorded before each filesystem change."""

    class State(models.TextChoices):
        INTENT = ("intent", "Started")
        DONE = ("done", "Done")
        SKIPPED = ("skipped", "Skipped")
        FAILED = ("failed", "Failed")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(ProjectionRun, on_delete=models.CASCADE, related_name="actions")
    plan_action = models.ForeignKey(ProjectionPlanAction, on_delete=models.SET_NULL, null=True, related_name="+")
    ordinal = models.PositiveIntegerField()
    action = models.CharField(max_length=16)
    kind = models.CharField(max_length=16)
    relative_path = models.TextField()
    state = models.CharField(max_length=16, choices=State.choices, default=State.INTENT)
    result = models.CharField(max_length=24, blank=True, default="")
    message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["run", "ordinal"]
