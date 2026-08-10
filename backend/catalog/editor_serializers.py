from rest_framework import serializers


class StringListField(
    serializers.ListField
):
    child = serializers.CharField(
        max_length=255,
        allow_blank=False,
    )

    def to_internal_value(
        self,
        data,
    ):
        values = super().to_internal_value(
            data
        )

        result = []
        seen = set()

        for value in values:
            cleaned = value.strip()

            if not cleaned:
                continue

            key = cleaned.casefold()

            if key in seen:
                continue

            seen.add(key)
            result.append(cleaned)

        return result


class ExternalIdsField(
    serializers.DictField
):
    child = serializers.CharField(
        max_length=255,
        allow_blank=False,
    )

    def to_internal_value(
        self,
        data,
    ):
        values = super().to_internal_value(
            data
        )

        return {
            str(key).strip(): str(value).strip()
            for key, value in values.items()
            if str(key).strip()
            and str(value).strip()
        }


class MetadataEditBaseSerializer(
    serializers.Serializer
):
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        write_only=True,
    )


class MovieMetadataEditSerializer(
    MetadataEditBaseSerializer
):
    title = serializers.CharField(
        required=False,
        max_length=1024,
    )

    sort_title = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1024,
    )

    original_title = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1024,
    )

    year = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1800,
        max_value=3000,
    )

    release_date = serializers.DateField(
        required=False,
        allow_null=True,
    )

    description = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    tagline = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    content_rating = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=64,
    )

    genres = StringListField(
        required=False,
    )

    studios = StringListField(
        required=False,
    )

    external_ids = ExternalIdsField(
        required=False,
    )


class SeriesMetadataEditSerializer(
    MetadataEditBaseSerializer
):
    title = serializers.CharField(
        required=False,
        max_length=1024,
    )

    sort_title = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1024,
    )

    original_title = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1024,
    )

    start_year = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1800,
        max_value=3000,
    )

    end_year = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1800,
        max_value=3000,
    )

    description = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    tagline = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    content_rating = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=64,
    )

    genres = StringListField(
        required=False,
    )

    studios = StringListField(
        required=False,
    )

    external_ids = ExternalIdsField(
        required=False,
    )

    def validate(
        self,
        attrs,
    ):
        start_year = attrs.get(
            "start_year",
            getattr(
                self.instance,
                "start_year",
                None,
            ),
        )

        end_year = attrs.get(
            "end_year",
            getattr(
                self.instance,
                "end_year",
                None,
            ),
        )

        if (
            start_year
            and end_year
            and end_year < start_year
        ):
            raise serializers.ValidationError(
                {
                    "end_year": (
                        "End year cannot be before "
                        "start year."
                    )
                }
            )

        return attrs


class SeasonMetadataEditSerializer(
    MetadataEditBaseSerializer
):
    title = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1024,
    )

    description = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    external_ids = ExternalIdsField(
        required=False,
    )


class EpisodeMetadataEditSerializer(
    MetadataEditBaseSerializer
):
    title = serializers.CharField(
        required=False,
        max_length=1024,
    )

    sort_title = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1024,
    )

    original_title = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1024,
    )

    air_date = serializers.DateField(
        required=False,
        allow_null=True,
    )

    description = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    content_rating = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=64,
    )

    genres = StringListField(
        required=False,
    )

    studios = StringListField(
        required=False,
    )

    absolute_number = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
    )

    external_ids = ExternalIdsField(
        required=False,
    )


class MediaVersionEditSerializer(
    MetadataEditBaseSerializer
):
    name = serializers.CharField(
        required=False,
        max_length=255,
    )

    edition = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
    )

    notes = serializers.CharField(
        required=False,
        allow_blank=True,
    )
