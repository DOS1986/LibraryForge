from django.contrib import admin

from catalog.models import (
    ArtworkFile,
    CanonicalFieldState,
    Episode,
    MediaVersion,
    MetadataChangeSet,
    Season,
    SemanticMatch,
    Series,
)


admin.site.register(Series)
admin.site.register(Season)
admin.site.register(Episode)
admin.site.register(MediaVersion)
admin.site.register(SemanticMatch)
admin.site.register(CanonicalFieldState)
admin.site.register(MetadataChangeSet)
admin.site.register(ArtworkFile)
