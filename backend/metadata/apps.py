from django.apps import AppConfig


class MetadataConfig(
    AppConfig
):
    name = "metadata"

    def ready(self):
        # The legacy NFO service also parses files during scans. Route its
        # parser through the guarded parser so size/DTD/entity checks apply
        # to scanned NFO files as well as API validation and writes.
        from metadata.services import (
            nfo as nfo_service,
        )
        from metadata.services.secure_nfo import (
            parse_nfo_content,
        )

        nfo_service.parse_nfo_content = (
            parse_nfo_content
        )
