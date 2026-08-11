# LibraryForge Integrations

LibraryForge is a library manager. Integrations exist to help LibraryForge understand, correct, enrich, organize, or project media that already exists.

## Product boundary

LibraryForge integrations may provide four capabilities:

- `metadata` — read metadata fields for existing media identities.
- `artwork` — read artwork references for existing media identities.
- `catalog` — read relationships among existing items, such as Channel → Video → Playlist.
- `output` — send/project LibraryForge-managed metadata to an external target.

LibraryForge deliberately has **no acquisition capability**. Integrations must not add download queues, subscriptions, torrent/NZB handling, automated grabbing, YouTube downloading, or *arr-style acquisition workflows.

## Connection model

Connections are configured once under **Settings → Integrations**. A library then opts into one or more configured connections under **Library Settings → Integrations**.

This separates user/server credentials from individual libraries and allows one configured connection to be reused safely across multiple libraries owned by the same LibraryForge user.

## Credential ownership model

Not every provider uses the same credential model. Provider definitions explicitly declare one of:

- `none` — no credential is required.
- `user` — the LibraryForge installation owner supplies the provider/server credential.
- `application` — LibraryForge uses a project/application credential registered for LibraryForge; there may be no end-user credential field.
- `hybrid` — LibraryForge uses a project/application credential plus an optional or required user-specific credential.

This distinction is intentionally part of the provider registry rather than the database schema. Adding TMDb, TheTVDB, OMDb, Fanart.tv, Jellyfin, or another adapter later does not require adding provider-name choices to a model.

`ProviderDefinition.fields` are the connection settings that an end user can configure. An application/project credential is managed by the provider implementation and is not exposed as a normal user-secret field.

The base provider implementation can read application-managed credentials from the Django setting `LIBRARYFORGE_INTEGRATION_APPLICATION_CREDENTIALS`. Future application/hybrid adapters can also override that behavior if a provider explicitly permits a bundled project credential. This setting is server-side only and is never serialized to the frontend.

See `docs/INTEGRATION_PROVIDER_POLICY.md` for the provider-by-provider policy matrix and official-source references.

## Alpha 0.1.0-alpha.4 providers

### YouTube

Capabilities: `metadata`, `artwork`, `catalog`.
Credential mode: `user`.

The YouTube adapter uses the official YouTube Data API only for existing stable IDs already known to LibraryForge. It does not search for content to acquire and cannot download media.

Each LibraryForge installation supplies its own YouTube Data API v3 key. LibraryForge does not ship a shared/global YouTube API key.

YouTube API responses are treated as live/transient provider data. LibraryForge does not persist provider response snapshots in alpha.4. This keeps archived/local metadata distinct from current provider state and avoids uncontrolled long-lived provider snapshots.

### TubeArchivist

Capabilities: `metadata`, `artwork`, `catalog`.
Credential mode: `user`.

The TubeArchivist adapter connects over HTTP(S) with the user's TubeArchivist API token. LibraryForge does not require a shared `/cache` mount and does not assume the two applications run in the same container, VM, or host.

The integration is read-only from LibraryForge's perspective. It does not manage TubeArchivist subscriptions, download queues, reindex operations, or deletion.

## Secrets

User-supplied provider secrets are submitted to the Django backend and encrypted before storage. They are never returned to the browser after saving. Encryption is derived from the LibraryForge Django secret key, so `DJANGO_SECRET_KEY` must remain stable for the life of the installation.

Application/project credentials used by future `application` or `hybrid` providers are not ordinary per-user connection fields and should be managed by the provider implementation according to that provider's terms.

## Future providers

The provider registry is intentionally extensible. Planned later milestones can register adapters without redesigning the settings model:

- alpha.5: TMDb, TheTVDB, OMDb, Fanart.tv and other metadata/artwork providers.
- alpha.6: Jellyfin, Emby, Kodi and other output/server integrations.

Only implemented providers should appear in the UI.
