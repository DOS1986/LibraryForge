from __future__ import annotations

from rest_framework import serializers

from integrations.crypto import decrypt_secrets, encrypt_secrets
from integrations.models import IntegrationConnection, LibraryIntegration
from integrations.registry import get_provider_class


class IntegrationConnectionSerializer(serializers.ModelSerializer):
    secrets = serializers.DictField(
        child=serializers.CharField(allow_blank=True),
        write_only=True,
        required=False,
    )
    configured_secret_fields = serializers.SerializerMethodField()
    provider_label = serializers.SerializerMethodField()
    capabilities = serializers.SerializerMethodField()
    credential_mode = serializers.SerializerMethodField()
    credential_summary = serializers.SerializerMethodField()

    class Meta:
        model = IntegrationConnection
        fields = [
            "id",
            "name",
            "provider",
            "provider_label",
            "enabled",
            "configuration",
            "secrets",
            "configured_secret_fields",
            "capabilities",
            "credential_mode",
            "credential_summary",
            "status",
            "last_tested_at",
            "last_error",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["status", "last_tested_at", "last_error"]

    def get_provider_label(self, obj):
        return get_provider_class(obj.provider).definition.label

    def get_configured_secret_fields(self, obj):
        try:
            values = decrypt_secrets(obj.encrypted_secrets)
        except ValueError:
            return []
        return sorted(key for key, value in values.items() if value)

    def get_capabilities(self, obj):
        return list(get_provider_class(obj.provider).definition.capabilities)

    def get_credential_mode(self, obj):
        return get_provider_class(obj.provider).definition.credential_mode

    def get_credential_summary(self, obj):
        return get_provider_class(obj.provider).definition.credential_summary

    def validate_name(self, value):
        request = self.context["request"]
        queryset = IntegrationConnection.objects.filter(owner=request.user, name=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("You already have an integration connection with this name.")
        return value

    def validate(self, attrs):
        provider_key = attrs.get("provider") or getattr(self.instance, "provider", "")
        try:
            provider_class = get_provider_class(provider_key)
        except ValueError as exc:
            raise serializers.ValidationError({"provider": str(exc)}) from exc
        definition = provider_class.definition

        configuration = dict(getattr(self.instance, "configuration", {}) or {})
        configuration.update(attrs.get("configuration") or {})

        secrets = {}
        if self.instance:
            secrets.update(decrypt_secrets(self.instance.encrypted_secrets))
        for key, value in (attrs.get("secrets") or {}).items():
            if value != "":
                secrets[key] = value

        allowed_config = {field.name for field in definition.fields if not field.secret}
        allowed_secrets = {field.name for field in definition.fields if field.secret}
        configuration = {key: value for key, value in configuration.items() if key in allowed_config}
        secrets = {key: value for key, value in secrets.items() if key in allowed_secrets}

        provider = provider_class(configuration=configuration, secrets=secrets)
        provider.validate()

        attrs["configuration"] = configuration
        attrs["_resolved_secrets"] = secrets
        return attrs

    def create(self, validated_data):
        secrets = validated_data.pop("_resolved_secrets", {})
        validated_data.pop("secrets", None)
        validated_data["owner"] = self.context["request"].user
        validated_data["encrypted_secrets"] = encrypt_secrets(secrets)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        secrets = validated_data.pop("_resolved_secrets", None)
        validated_data.pop("secrets", None)
        if secrets is not None:
            validated_data["encrypted_secrets"] = encrypt_secrets(secrets)
        return super().update(instance, validated_data)


class LibraryIntegrationSerializer(serializers.ModelSerializer):
    connection_name = serializers.CharField(source="connection.name", read_only=True)
    provider = serializers.CharField(source="connection.provider", read_only=True)
    provider_label = serializers.SerializerMethodField()

    def get_provider_label(self, obj):
        return get_provider_class(obj.connection.provider).definition.label

    class Meta:
        model = LibraryIntegration
        fields = [
            "id",
            "library",
            "connection",
            "connection_name",
            "provider",
            "provider_label",
            "enabled",
            "priority",
            "capabilities",
            "credential_mode",
            "credential_summary",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        request = self.context["request"]
        library = attrs.get("library") or getattr(self.instance, "library", None)
        connection = attrs.get("connection") or getattr(self.instance, "connection", None)

        if not library or library.owner_id != request.user.id:
            raise serializers.ValidationError({"library": "Library not found."})
        if not connection or connection.owner_id != request.user.id:
            raise serializers.ValidationError({"connection": "Integration connection not found."})

        definition = get_provider_class(connection.provider).definition
        requested = attrs.get("capabilities")
        if requested is None:
            requested = getattr(self.instance, "capabilities", None) or list(definition.capabilities)

        valid = set(definition.capabilities)
        normalized = [item for item in dict.fromkeys(requested) if item in valid]
        if not normalized:
            raise serializers.ValidationError({"capabilities": "Select at least one supported capability."})

        attrs["capabilities"] = normalized
        return attrs
