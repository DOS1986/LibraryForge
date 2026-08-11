from django.contrib import admin

from catalog.models import (
    ArtworkFile,
    CanonicalFieldState,
    Channel,
    Episode,
    MediaVersion,
    MetadataChangeSet,
    OnlineVideo,
    Playlist,
    PlaylistMembership,
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
admin.site.register(Channel)
admin.site.register(OnlineVideo)
admin.site.register(Playlist)
admin.site.register(PlaylistMembership)
