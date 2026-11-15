from rest_framework import serializers

from .models import ScanJob


class ScanJobSerializer(serializers.ModelSerializer):
    progress_percent = serializers.FloatField(read_only=True)

    library_name = serializers.CharField(
        source="library.name",
        read_only=True,
    )

    status_label = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )
    waiting_for_worker = serializers.SerializerMethodField()
    stalled = serializers.SerializerMethodField()

    def _live_workers(self):
        # Computed once per response, not once per job.
        if "live_workers" not in self.context:
            from jobs.services import live_worker_ids

            self.context["live_workers"] = live_worker_ids()
        return self.context["live_workers"]

    def get_waiting_for_worker(self, obj):
        """Queued, and no scan worker is running to pick it up."""

        return obj.status == ScanJob.Status.QUEUED and not self._live_workers()

    def get_stalled(self, obj):
        """Looks active, but the worker that was running it has stopped."""

        from jobs.services import is_stalled

        return is_stalled(obj, self._live_workers())

    class Meta:
        model = ScanJob

        fields = [
            "id",
            "library",
            "library_name",
            "status",
            "status_label",
            "waiting_for_worker",
            "stalled",
            "cancel_requested",
            "total_files",
            "processed_files",
            "total_media_files",
            "processed_media_files",
            "total_nfo_files",
            "processed_nfo_files",
            "progress_percent",
            "current_path",
            "created_count",
            "updated_count",
            "skipped_count",
            "nfo_created_count",
            "nfo_updated_count",
            "error_count",
            "errors",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        ]

        read_only_fields = fields
