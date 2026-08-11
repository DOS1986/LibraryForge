from __future__ import annotations

from collections import defaultdict
from typing import Any

from integrations.crypto import decrypt_secrets
from integrations.models import LibraryIntegration
from integrations.registry import get_provider_class


def provider_for_connection(connection):
    provider_class = get_provider_class(connection.provider)
    return provider_class(
        configuration=connection.configuration,
        secrets=decrypt_secrets(connection.encrypted_secrets),
    )


def active_links_for_library(*, library, capability: str | None = None):
    queryset = (
        LibraryIntegration.objects
        .filter(
            library=library,
            enabled=True,
            connection__enabled=True,
        )
        .select_related("connection")
        .order_by("priority", "created_at")
    )

    links = list(queryset)
    if capability:
        links = [
            link
            for link in links
            if capability in (link.capabilities or [])
        ]
    return links


def transient_lookup(*, library, target_type: str, source_id: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for link in active_links_for_library(library=library, capability="metadata"):
        provider = provider_for_connection(link.connection)
        try:
            item = provider.lookup_one(target_type=target_type, source_id=source_id)
        except Exception as exc:
            output.append(
                {
                    "connection_id": str(link.connection_id),
                    "connection_name": link.connection.name,
                    "provider": link.connection.provider,
                    "ok": False,
                    "error": str(exc),
                }
            )
            continue
        output.append(
            {
                "connection_id": str(link.connection_id),
                "connection_name": link.connection.name,
                "provider": link.connection.provider,
                "ok": True,
                "data": item,
            }
        )
    return output


def apply_artwork_fallbacks(*, user, rows: list[dict[str, Any]], target_type: str) -> None:
    """Attach a lazy LibraryForge artwork proxy to rows lacking local artwork.

    No provider network requests happen during catalog pagination. The image
    endpoint tries assigned artwork integrations in priority order only when the
    browser requests the image.
    """

    by_library: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("artwork_url") or not row.get("source_id") or not row.get("library"):
            continue
        by_library[str(row["library"])].append(row)

    if not by_library:
        return

    from libraries.models import Library

    libraries = {
        str(item.id): item
        for item in Library.objects.filter(owner=user, id__in=by_library.keys())
    }

    for library_id, library_rows in by_library.items():
        library = libraries.get(library_id)
        if library is None:
            continue

        links = active_links_for_library(library=library, capability="artwork")
        if not links:
            continue

        # Prime any batch-capable YouTube lookup once for this catalog page.
        # The image endpoint then reuses the short-lived cache instead of
        # spending one YouTube quota unit per visible image.
        source_ids = [str(row["source_id"]) for row in library_rows]
        for link in links:
            if link.connection.provider != "youtube":
                continue
            try:
                provider_for_connection(link.connection).lookup_many(
                    target_type=target_type,
                    source_ids=source_ids,
                )
            except Exception:
                pass

        for row in library_rows:
            row["artwork_url"] = (
                f"/api/integrations/libraries/{library_id}/artwork/"
                f"?target_type={target_type}&source_id={row['source_id']}"
            )
            row["artwork_source"] = "integration"
