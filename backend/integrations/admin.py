from django.contrib import admin

from integrations.models import IntegrationConnection, LibraryIntegration


@admin.register(IntegrationConnection)
class IntegrationConnectionAdmin(admin.ModelAdmin):
    list_display = ("name", "provider", "owner", "enabled", "status", "last_tested_at")
    list_filter = ("provider", "enabled", "status")
    search_fields = ("name", "owner__email")


@admin.register(LibraryIntegration)
class LibraryIntegrationAdmin(admin.ModelAdmin):
    list_display = ("library", "connection", "enabled", "priority")
    list_filter = ("enabled", "connection__provider")
