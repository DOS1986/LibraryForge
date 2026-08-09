from rest_framework import serializers

from .models import (
    OutputProfile,
    Projection,
)


class OutputProfileSerializer(
    serializers.ModelSerializer
):
    target_label = serializers.CharField(
        source="get_target_display",
        read_only=True,
    )

    class Meta:
        model = OutputProfile

        fields = [
            "id",
            "name",
            "target",
            "target_label",
            "nfo_root_element",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]


class ProjectionSerializer(
    serializers.ModelSerializer
):
    output_profile_name = (
        serializers.CharField(
            source="output_profile.name",
            read_only=True,
        )
    )

    output_target = serializers.CharField(
        source="output_profile.target",
        read_only=True,
    )

    link_mode_label = (
        serializers.CharField(
            source="get_link_mode_display",
            read_only=True,
        )
    )

    class Meta:
        model = Projection

        fields = [
            "id",
            "library",
            "output_profile",
            "output_profile_name",
            "output_target",
            "name",
            "destination_path",
            "link_mode",
            "link_mode_label",
            "naming_template",
            "generate_nfo",
            "last_run_at",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "last_run_at",
            "created_at",
            "updated_at",
        ]
