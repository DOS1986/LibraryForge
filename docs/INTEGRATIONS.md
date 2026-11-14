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

## Metadata provider contract (alpha.5)

Movie and series metadata providers extend the same integration system; there is no separate metadata registry or credential store.

- `ProviderDefinition.metadata_target_types` declares which normalized targets a provider can search and describe: `movie` and/or `series` (a whole television series, never an episode or season). It defaults to `()`, so existing providers are unaffected. Declaring a target requires the `metadata` capability.
- `IntegrationProvider.supports_metadata_target(target_type)` answers whether the provider's definition supports a target. It says what a provider *can* do; it does not grant access to a connection, library assignment, or user.
- `IntegrationProvider.search_metadata(target_type=, query=, year=, language=, page=, limit=)` returns a list of `MetadataCandidate` values. An empty list is a successful "no results" answer.
- `IntegrationProvider.get_metadata(target_type=, source_id=, language=)` returns one `ProviderMetadata` value.

The public methods validate the request before any network call (unsupported targets, empty or oversized queries, invalid years, pages, limits, languages, and source IDs fail without contacting the provider) and validate the adapter's output afterwards (results must be normalized types for the same provider and target). Adapters implement only `_search_metadata` and `_get_metadata`.

The normalized types live in `backend/metadata/providers/types.py`: `MetadataCandidate`, `ProviderMetadata`, `ProviderArtwork`, `ExternalId`, `ContentRating`, and `PartialDate`. Identities are scoped by provider, target type, and source ID. Dates keep their known precision (a year is not January 1). Missing provider values stay empty and never imply clearing catalog data. `ProviderMetadata.raw` is optional, bounded, internal diagnostic data that is excluded from `to_dict()` and must never be a merge source. Failures raise `MetadataProviderError` with a stable `category` (`unsupported_target`, `invalid_request`, `invalid_configuration`, `invalid_credentials`, `permission_denied`, `not_found`, `rate_limited`, `unavailable`, `timeout`, `malformed_response`) and an explicit `retryable` flag.

Search and detail retrieval never write catalog data. Applying provider metadata is a separate, reviewed step owned by the metadata services. `integrations.registry.metadata_provider_classes(target_type)` lists registered providers that declare a target; YouTube and TubeArchivist declare none and keep their existing known-ID lookups.

## Metadata matching (alpha.5)

Movies and series have a **Match** tab in the catalog item editor. It searches an assigned metadata provider, explains each candidate, and previews the provider's details beside the catalog's values. It is review only: matching never changes catalog metadata, field provenance, or change history.

Read-only endpoints (GET only, owner-scoped; anything not owned is a 404):

- `GET /api/metadata-match/<movie|series>/<id>/` returns the target, its eligible provider connections, and search defaults (current title and year).
- `GET /api/metadata-match/<movie|series>/<id>/search/?connection=&query=&year=&page=` returns candidates with match hints.
- `GET /api/metadata-match/<movie|series>/<id>/preview/?connection=&source_id=&territory=` returns a field-by-field comparison.

**Eligibility.** A connection can serve a target only when it is enabled, owned by the library's owner, assigned to the target's library with the `metadata` capability, and its provider declares the target type. Other assigned connections are listed as unavailable with a reason, and no request is sent to them. With exactly one eligible connection it is used automatically; otherwise the request must name one.

**Match hints.** Each candidate gets a tier (`strong`, `likely`, `possible`, `weak`, or `conflict`) and the reasons behind it: an external ID matching or conflicting, the title matching exactly, after normalization, or via the original title, and the year being the same, close, or different (with a possible-remake warning for the same title in a different year). Tiers are advisory labels, not probabilities, and never trigger an automatic change. A conflicting external ID always produces `conflict`.

**Preview rules.** Each field row has a status, whether it can be selected, and whether it is selected by default:

| Status | Meaning | Selectable | Default |
| --- | --- | --- | --- |
| `fill` | Catalog field is empty and the provider has a value | yes | selected |
| `different` | Both have values and they differ | yes | not selected |
| `add` | List field: the provider has entries the catalog lacks | yes | not selected |
| `unchanged` | Same value | no | — |
| `missing` | Provider didn't supply a value | no | — |
| `locked` | Field is locked by a manual edit | no | — |
| `conflict` | External ID differs from the catalog's | no | — |

- Existing values, including local and manual edits, are kept unless the person chooses otherwise. Locked fields must be unlocked in the Metadata tab first.
- Genres and studios only ever add entries; the preview shows the resulting list, and existing entries are never removed.
- A movie's release date is offered only when the provider has a full date. Choosing it also selects the linked year so the two stay consistent.
- The content rating uses one territory (`territory`, else the region from `language`, else `US`); every territory's rating is shown as an option.
- Data the catalog has nowhere to store (movie runtime, series episode runtime, TV networks) is listed under "not stored" instead of being mapped onto another field.
- `target_revision` and `provider_snapshot` fingerprint the catalog values, locks, and provider data that were shown, so a later apply step can refuse a stale review.

**Errors and limits.** Provider failures return `{"detail": ..., "error": {"category", "message", "retryable"}}` with HTTP 400 (invalid request or unsupported target), 404 (provider has no such record), 429 (rate limited, with `Retry-After` when known), 504 (timeout), or 502 (other provider failures). Search and preview share a per-user budget, `LIBRARYFORGE_METADATA_PROVIDER_RATE` (default `60/min`). The provider's attribution notice is shown with its data.

## Failure behavior

Integration failures must not change or remove managed media. Metadata and artwork lookups are enrichment-only operations.

If an assigned provider is unavailable, times out, or returns unusable artwork, LibraryForge falls through to the next eligible provider where possible. If no provider succeeds, the catalog remains usable and displays the local metadata/artwork state or a no-art placeholder.

Frontend API clients must not render raw server HTML error pages. Unexpected non-JSON server failures are reduced to a concise HTTP-status error while the detailed traceback remains server-side during development.

## Mixed libraries

Mixed libraries may contain Movie/TV and Online Video media together. LibraryForge routes a file through the Online Video resolver only when it has an explicit Online Video signal, such as:

- an existing Online Video semantic assignment,
- a detected TubeArchivist metadata source,
- a detected yt-dlp metadata source, or
- a validated TubeArchivist `<channel-id>/<video-id>` archive path.

Generic embedded title/artist metadata alone is not enough to classify a mixed-library file as Online Video.

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

## Alpha 0.1.0-alpha.5 providers

### TMDB

Capabilities: `metadata`.
Metadata targets: `movie`, `series`.
Credential mode: `user`.

The TMDB adapter (`integrations/providers/tmdb.py`) searches The Movie Database for movies and TV series and returns normalized candidates and details. It does not write catalog metadata; applying provider data is a later, reviewed step.

- **Credential.** Each installation supplies its own TMDB *API Read Access Token* (themoviedb.org → Settings → API). It is stored encrypted and sent only from the backend as `Authorization: Bearer`, so it never appears in request URLs or logs of URLs. The connection test calls the small `/3/configuration` endpoint.
- **Search.** Movies use `/3/search/movie` with `year`; series use `/3/search/tv` with `first_air_date_year`. Adult results are excluded. TMDB pages run from 1 to 500. Results keep TMDB's order; malformed individual results are skipped rather than failing the search.
- **Details.** `/3/movie/{id}` and `/3/tv/{id}` with `append_to_response` for external IDs, certifications/content ratings, and images, so one request returns everything a preview needs.
- **Field mapping.** Production companies map to `studios` and TV networks to `networks` (kept separate). Movie certifications come from `release_dates`, preferring the theatrical release per country; series ratings come from `content_ratings`. Audience scores such as `vote_average` are never mapped to content ratings. A series' `runtime_minutes` is its typical episode runtime (the first `episode_run_time` value). A series has an `end_date` only when TMDB reports it as Ended or Canceled. External IDs include `tmdb`, and `imdb`, `tvdb`, and `wikidata` when TMDB supplies valid values. Invalid dates and values are treated as missing.
- **Artwork.** Posters, backdrops, and logos become `ProviderArtwork` references at `https://image.tmdb.org/t/p/original/...` with TMDB's dimensions and language. Search candidates use a `w342` poster. These are references only; nothing is downloaded or selected in this milestone slice.
- **Errors and retries.** HTTP 401/403 → `invalid_credentials`, 404 (and TMDB's HTTP-200 not-found codes) → `not_found`, 429 → `rate_limited` (with `retry_after_seconds` when TMDB sends `Retry-After`), 5xx → `unavailable`, timeouts → `timeout`, unreadable bodies → `malformed_response`. Retryable failures get at most one inline retry after a short jittered wait, or after `Retry-After` if it is 2 seconds or less. Credential and validation failures are never retried.
- **Caching.** Successful responses are cached briefly in the Django cache (search 15 minutes, details 1 hour), scoped to a hash of the credential so different connections never share results. TMDB's terms forbid caching for longer than 6 months.
- **Terms and attribution.** TMDB's API terms apply to each installation's use, including their non-commercial license. LibraryForge shows TMDB's required notice in the provider description and on **System → Credits**: "This product uses TMDB and the TMDB APIs but is not endorsed, certified, or otherwise approved by TMDB."

## Secrets

User-supplied provider secrets are submitted to the Django backend and encrypted before storage. They are never returned to the browser after saving. Encryption is derived from the LibraryForge Django secret key, so `DJANGO_SECRET_KEY` must remain stable for the life of the installation.

Application/project credentials used by future `application` or `hybrid` providers are not ordinary per-user connection fields and should be managed by the provider implementation according to that provider's terms.

## Future providers

The provider registry is intentionally extensible. Planned later milestones can register adapters without redesigning the settings model:

- alpha.5 and later: TheTVDB, OMDb, Fanart.tv and other metadata/artwork providers (TMDB is implemented).
- alpha.6: Jellyfin, Emby, Kodi and other output/server integrations.

Only implemented providers should appear in the UI.
