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

    class Meta:
        model = ScanJob

        fields = [
            "id",
            "library",
            "library_name",
            "status",
            "status_label",
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
