from django.contrib import admin

from preferences.models import SystemAction, UserSettings


@admin.register(UserSettings)
class UserSettingsAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "display_name",
        "default_page_size",
        "show_build_information",
        "updated_at",
    ]
    search_fields = [
        "user__email",
        "display_name",
    ]


@admin.register(SystemAction)
class SystemActionAdmin(admin.ModelAdmin):
    list_display = [
        "action",
        "actor",
        "created_at",
    ]
    list_filter = ["action"]
    search_fields = ["actor__email"]
    readonly_fields = [
        "actor",
        "action",
        "metadata",
        "created_at",
    ]
