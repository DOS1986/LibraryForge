from django.contrib import admin

from catalog.models import (
    Episode,
    MediaVersion,
    Season,
    SemanticMatch,
    Series,
)


admin.site.register(Series)
admin.site.register(Season)
admin.site.register(Episode)
admin.site.register(MediaVersion)
admin.site.register(SemanticMatch)
