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

Movies and series have a **Match** tab in the catalog item editor. It searches an assigned metadata provider, explains each candidate, previews the provider's details beside the catalog's values, and applies only the fields the person chooses and confirms. Search, context, and preview never change catalog metadata, field provenance, or change history; only the apply endpoint writes.

Read-only endpoints (GET only, owner-scoped; anything not owned is a 404):

- `GET /api/metadata-match/<movie|series>/<id>/` returns the target, its eligible provider connections, and search defaults (current title and year).
- `GET /api/metadata-match/<movie|series>/<id>/search/?connection=&query=&year=&page=` returns candidates with match hints.
- `GET /api/metadata-match/<movie|series>/<id>/preview/?connection=&source_id=&territory=` returns a field-by-field comparison.
- `POST /api/metadata-match/<movie|series>/<id>/apply/` applies chosen fields from a reviewed preview (see below).

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
- `target_revision` and `provider_snapshot` fingerprint the catalog values, locks, and provider data that were shown, so apply can refuse a stale review.
- A field locked by a previous provider apply does not block a new match; manual (and other) locks always do.

**Applying a reviewed preview.** The request carries only identifiers and field *names*: `connection`, `source_id`, `territory`, `fields`, `target_revision`, `provider_snapshot`, and a client-generated `operation_id`. Values in the request are ignored. The server:

1. Returns the recorded result if `operation_id` was already used for the same user, target, and plan; a reused ID with a different plan is refused (`409`, `operation_reused`).
2. Rebuilds the preview, retrieving provider data outside any database transaction, and refuses the apply if the provider data (`409`, `provider_changed`) or the item's values or locks (`409`, `target_changed`) no longer match what was reviewed.
3. Accepts only fields the rebuilt preview marks selectable (`400` otherwise). Choosing a movie's release date brings its year along; a year that would disagree with the release date, or a last-aired year before the first-aired year, is refused.
4. In one transaction, locks the item row, re-checks its revision, writes the server-side values, and records provenance and history. Any failure rolls back all of it.

Provenance: each applied field's `CanonicalFieldState` gets source `provider`, `source_ref` `<provider>:<movie|series>:<source id>`, and is **locked**, because library scans rewrite unlocked title, year, sort title, and first-aired year from filenames and folders. A later reviewed match can still replace a provider-locked value, and a manual edit takes over the field as usual. Each apply also creates a `MetadataChangeSet` with source `provider`, the old and new value of each applied field, the actor, the `operation_id`, and secret-free `details` (provider, connection, source ID, territory, retrieval time, requested and applied fields, and the reviewed fingerprints). It appears in the History tab. There is no automatic undo; earlier values are kept in the change set.

**Errors and limits.** Provider failures return `{"detail": ..., "error": {"category", "message", "retryable"}}` with HTTP 400 (invalid request or unsupported target), 404 (provider has no such record), 429 (rate limited, with `Retry-After` when known), 504 (timeout), or 502 (other provider failures). Search, preview, and apply share a per-user budget, `LIBRARYFORGE_METADATA_PROVIDER_RATE` (default `60/min`). The provider's attribution notice is shown with its data.

## Content ratings (alpha.5)

Each library has a **Ratings** tab for parental-control coverage. It covers every kind of item the library contains: **movies**, **TV series**, and **online video channels** (YouTube/TubeArchivist channels, presented to media servers as TV series, whose videos use the channel's rating). A mixed library lists each kind it holds, and the coverage response's `kinds` says which kinds exist and whether provider suggestions and NFO import/export apply to each. Items are counted and listed by rating status:

- `rated`: a recognized US rating. Movies use MPA ratings (`G`, `PG`, `PG-13`, `R`, `NC-17`) and TV uses TV Parental Guidelines (`TV-Y`, `TV-Y7`, `TV-Y7-FV`, `TV-G`, `TV-PG`, `TV-14`, `TV-MA`). Both sets count as recognized for either kind, because media servers such as Jellyfin compare them on one scale.
- `missing`: no rating.
- `unrecognized`: some other value, such as a UK `15` or `NR`, which a media server may not be able to filter on.

Endpoints (GET only, owner-scoped; neither changes catalog data):

- `GET /api/libraries/<id>/ratings/?kind=<movie|series>&status=<missing|unrecognized|rated|all>&search=&page=&page_size=` returns per-kind counts and a page of items with their rating, status, and rating source/lock.
- `GET /api/libraries/<id>/ratings/suggestions/?kind=<movie|series>&ids=<id,...>` takes up to 10 items from that library. For each one it searches the library's metadata provider with the item's title and year (retrying without the year if nothing is found), and only uses a `strong` or `likely` match. It then builds the normal match preview and returns one of:
  - `suggested`, with the rating and the exact apply payload for the `content_rating` field
  - `needs_review` (no confident match)
  - `no_rating` (the provider has no rating for the territory; other countries are listed)
  - `locked` (manual lock)
  - `unchanged`
  - `error` (provider failure, reported per item)

The Ratings tab's **Find ratings** button covers every unrated item on the current page (25, 50, 100, or 200 per page) by sending these requests in sequential batches of 10, with progress and a Stop button. Each batch counts once against the metadata provider rate limit, as does each Apply; raise `LIBRARYFORGE_METADATA_PROVIDER_RATE` if you work through large pages quickly.

**Several providers.** With more than one movie/TV provider assigned to a library (for example TMDB and OMDb), suggestions try them in the library's priority order (Library Settings → Integrations) unless a `connection` is given. A real rating from any provider wins and ends the chain. Otherwise the most useful fallback is kept: an estimate, then "no rating", then "needs review". Providers declare the external-ID namespace of their source IDs (`metadata_id_namespace`: `tmdb`, `imdb`). An item that already has that ID, or that an earlier provider's match revealed (TMDB's details include the IMDb ID), is looked up directly instead of searched by title. Each result says which provider it came from and which were tried.

A suggested rating is saved only when the person clicks **Apply** for that item. That call goes through the metadata-match apply endpoint, so the stale-review checks, provenance, history, scan protection, and duplicate-submission handling all apply. Items that need review can be opened in the catalog editor's Match tab from the list. Suggestions share the metadata provider rate limit.

### Estimated US ratings

When the provider has no US rating for a title but has other countries' ratings, the preview and rating suggestions offer an **estimated** US rating (`metadata/services/rating_equivalents.py`):

1. Each country's rating is converted to the minimum age it implies, using tables for about 20 systems (UK, Ireland, Canada, Australia, New Zealand, Germany, Austria, Switzerland, France, the Netherlands, Belgium, Spain, Portugal, Italy, Brazil, Mexico, the Nordic countries, Japan, Korea, India). Plain age values such as `12`, `16+`, or `FSK 12` are read in any system; unknown values are ignored.
2. The upper middle of those ages is taken (the median, rounding toward the stricter side), so a single unusual country doesn't decide the result.
3. That age maps to the US scale:
   - movies: G (0), PG (up to 9), PG-13 (10–14), R (15+)
   - TV: TV-G (0), TV-PG (up to 9), TV-14 (10–14), TV-MA (15+)

   TV-Y and TV-Y7 mean *made for children*, which an age can't tell, so they are never estimated.

Estimated rows are marked `estimated` with the `estimate` basis, are never pre-selected, and are saved only by an explicit action (**Apply estimated …** on the Ratings tab, or **Save estimated …** in the Match tab). The change set records them under `details.estimated_fields`, and its note says the rating was estimated. Estimates are only made for the US territory.

### Setting ratings by hand

`POST /api/libraries/<id>/ratings/set/` with `{"kind": "movie|series|channel", "ids": [...], "rating": "TV-Y"}` sets the rating on up to 500 items from that library, or clears it with `""`. Recognized US ratings are upper-cased. Each change is recorded like a manual edit: the field gets a manual, locked provenance record and a history entry, so NFO imports and provider suggestions won't replace it. Unchanged items are counted but not rewritten. On the Ratings tab, select rows (or all on the page), choose a rating, and confirm. Metadata providers don't rate online video channels, so channels are rated here, optionally starting from YouTube hints (below).

### YouTube rating hints for channels

YouTube doesn't rate videos, but the YouTube Data API returns two audience flags: `status.madeForKids` on channels and videos, and `contentDetails.contentRating.ytRating = "ytAgeRestricted"` on videos YouTube has age-restricted. For channel rows, **Check YouTube** turns them into a suggested US TV rating, strongest signal first:

1. Any checked video is age-restricted: **TV-MA**.
2. The channel is marked made for kids: **TV-Y**.
3. At least 90% of the checked videos are made for kids: **TV-Y**.
4. Otherwise no hint. Most general-audience content has no flag, so you rate it yourself.

TV-Y is a starting point: for a made-for-kids channel aimed at older children, TV-Y7 may fit better, and the hint says so.

- **Endpoints.** `GET /api/libraries/<id>/ratings/youtube-hints/?ids=…` returns a hint, reason, flag counts, and what applying would do (`set`, `change`, `unchanged`, or `locked`) for up to 25 channels. It never writes. `POST` with `{"hints": {"<channel id>": "TV-Y"}}` recomputes each hint and writes only those that still equal the reviewed rating. Both use the metadata provider rate limit.
- **Connection.** Uses the YouTube connection assigned to the library for metadata (library **Settings**). Without one the endpoint answers 409 with that explanation.
- **Quota.** Channel IDs come from the catalog, and up to the 250 most recent videos LibraryForge has for each channel are checked. Requests are batched 50 IDs at a time (`channels.list part=status`, `videos.list part=status,contentDetails`), one quota unit per call. Flags are cached for an hour and never stored.
- **Provenance.** Applied hints are saved with provider provenance (`youtube:channel:<channel ID>`), locked against scans, with a history entry recording the flag counts. A later hint can update a hinted rating, but ratings set by hand are never replaced; one click applies hints only to channels with no rating, and replacing an existing rating is a per-row choice.
- **Limits.** Google documents `selfDeclaredMadeForKids` as owner-only, so only the effective `madeForKids` value is read. A channel's flag reflects its videos' default audience, not each video's content.

### Importing ratings from NFO files

`GET /api/libraries/<id>/ratings/nfo-import/?kind=<movie|series>` previews and `POST` (body `{"kind": ...}`) applies importing the `<mpaa>` rating from NFO files LibraryForge has already indexed. It reads stored, parsed NFO data and changes no files, so it works for read-only libraries.

- **Movie NFOs** are the indexed `movie` NFOs matched to each movie. `<movie file>.nfo` is preferred over a shared `movie.nfo`, and if a movie's NFOs carry different ratings it is reported as `nfo_disagree` and left alone.
- **`tvshow.nfo`** is linked to a series by folder: the deepest folder containing the `tvshow.nfo` that holds at least half of the series' episode files.
- **Normalization** handles Kodi spellings such as `Rated PG-13`, `US:R`, and `US:PG-13 / UK:12A`. Recognized US ratings are upper-cased; other values (for example `Not Rated` or `15`) are kept as written and show as unrecognized.
- **Outcomes per item:** `set` (empty rating filled), `update` (the current rating came from an earlier NFO import and the NFO changed), `unchanged`, `conflict` (a different rating from another source; kept), `locked` (manual or provider lock; kept), `nfo_disagree`, `no_rating_in_nfo`, `no_nfo`.
- **Writes** happen only for `set` and `update`, and the plan is recomputed at apply time with the rows locked, so a rating changed after the preview is never overwritten. Each imported rating records the NFO as its source (unlocked, so a later NFO change can update it again) and a history entry citing the NFO path. Running the import again is a no-op.

### Writing ratings into NFO files

`GET /api/libraries/<id>/ratings/nfo-export/?kind=<movie|series>` previews, and `POST` (body `{"kind", "cursor", "batch"}`) writes one batch, putting each item's LibraryForge rating into its existing NFO files' `<mpaa>`. Jellyfin and other media servers read their parental ratings from there. The Ratings tab runs batches of 100 with progress and a Stop button.

- **Library mode.** Only libraries in **Sidecar Only** or **Full Control** mode are written. Read-only libraries can be previewed, and a write returns `409` explaining how to change the mode (Library Settings → General → Management Mode).
- **Which files.** Only existing, successfully parsed movie NFOs (every NFO matched to the movie) and the `tvshow.nfo` linked to a series by folder. No NFO is created; rated items without one are reported as `no_nfo`.
- **What changes.** Only the `<mpaa>` value. An existing value is replaced, and an empty or self-closing tag is filled. If the tag is missing it is added just before the closing root tag, using the file's own indentation and line endings. Everything else is left byte-for-byte as it was, including comments, other tags, and CRLF line endings.
- **Safety checks.**
  - A file whose content differs from the indexed copy is skipped as `changed_on_disk` (rescan, then try again). Content is compared rather than timestamps, because media servers often re-save NFOs without changing them; line-ending differences alone don't count as a change.
  - The edited document is re-parsed and must still have the same root and the new rating before it is written.
  - Writes go through the hardened NFO writer, which confines paths to the library root, re-checks symlinks, writes to a temporary file, and replaces atomically.
  - Per-file failures are reported without stopping the batch.
- **Afterwards,** refresh the library's metadata in the media server so it re-reads the NFOs. If the media server's own NFO saver is enabled, it may later rewrite these files from its own metadata.

Episodes are not rated individually here. Media servers generally apply a series' rating to its episodes, but writing ratings into NFO files for Jellyfin is a separate step.

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

In alpha.5 the YouTube connection also supplies channel rating hints from YouTube's made-for-kids and age-restriction flags (see **YouTube rating hints for channels**).

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

### OMDb

Capabilities: `metadata`.
Metadata targets: `movie`, `series`.
ID namespace: `imdb`.
Credential mode: `user`.

The OMDb adapter (`integrations/providers/omdb.py`) uses the Open Movie Database, which serves IMDb-derived data, including the US certification (`Rated`) for most movies and many series. It is mainly a second source of real US ratings where TMDB has none.

- **Credential.** Each installation supplies its own OMDb API key (omdbapi.com; free keys allow 1,000 requests a day). OMDb only accepts the key as an `apikey` query parameter, so LibraryForge never logs or displays request URLs. The connection test looks up one well-known IMDb ID.
- **Search and details.** Search uses `s` with `type` and `y` (pages 1 to 100). OMDb's "not found" answer is a successful empty search. Details use `i=<IMDb ID>&plot=full`, and the record's `Type` must match the target, so a series ID is never applied to a movie.
- **Field mapping.**
  - `Rated` becomes the US content rating.
  - `Released` becomes the release date, unless it disagrees with `Year` (a later regional or re-release date), in which case only the year is kept.
  - A series' `Year` range (`2008–2013`) gives its end year; an open range (`2019–`) means still running.
  - `Runtime` gives minutes, `Genre` the genres, and `Production` the studio when present.
  - `Poster` is kept only as an https reference.
  - `N/A` means missing.
  - IMDb scores are never treated as ratings.
- **Errors.** OMDb error messages are classified by their wording: not found, invalid API key, request limit reached, and too many results. HTTP 401 is reported as a rejected key or an exhausted daily limit. Rate limits are not retried, because they reset daily; other transient errors get one retry.
- **Terms.** OMDb content is CC BY-NC 4.0, and its Terms of Use allow personal, non-commercial use and restrict archiving. LibraryForge keeps only short-lived caches (search 15 minutes, details 1 hour, scoped to the key); ratings a person saves stay in their own catalog. The Poster API is patron-only, so posters are never downloaded. Attribution appears in the provider description, with its data, and on **System → Credits**.

### TheTVDB

Capabilities: `metadata`.
Metadata targets: `movie`, `series`.
ID namespace: `tvdb`.
Credential mode: `user`.

The TheTVDB adapter (`integrations/providers/tvdb.py`) uses TheTVDB's v4 API. It is strongest for TV series, including older and regional shows, and their country content ratings.

- **Credential.** A TheTVDB v4 API key, plus a subscriber PIN for user-supported keys (optional field). `POST /login` exchanges them for a token that is valid for a month. The token is cached (renewed after 25 days, scoped to the key and PIN), sent as `Authorization: Bearer`, and renewed once automatically if TheTVDB refuses it. The connection test performs a fresh login.
- **Search and details.**
  - Search is `/search` with `type` (`series` or `movie`) and `year`, 20 per page; TheTVDB caps search at 5,000 results.
  - Details are `/series/{id}/extended` or `/movies/{id}/extended` with `meta=translations&short=true`.
  - English names and overviews are preferred when TheTVDB has them (three-letter `eng` translations), keeping the original title as the original title.
- **Field mapping.**
  - Series: first and last aired dates (the end date only once the status is Ended or Canceled), average runtime as the typical episode runtime, and the original/latest network.
  - Movies: first release date, runtime, and studio and production companies.
  - Genres, and remote IDs for IMDb and TMDB.
  - Content ratings per country. TheTVDB's country codes are read as two- or three-letter codes (`usa` becomes `US`), so the US rating is used directly and other countries feed the US estimate. Popularity `score` is never treated as a rating.
- **Provider chain.** TMDB's series details include the TVDB ID, so in multi-provider rating suggestions TheTVDB looks those series up directly instead of searching.
- **Errors.** 401 means a rejected key or PIN (after one token renewal); 400 and 404 mean not found (an empty search); 429 means rate limited; 5xx and timeouts get one retry.
- **Terms.** TheTVDB requires attribution with a direct link to TheTVDB.com, shown in the provider description, with its data, and on **System → Credits**. Personal and small projects are free; user-supported keys need TheTVDB's subscription PIN. No caching limits are stated; LibraryForge keeps short-lived caches (search 15 minutes, details 1 hour).

### Jellyfin

Capabilities: `output`.
Credential mode: `user`.

The Jellyfin adapter (`integrations/providers/jellyfin.py`) connects to your own Jellyfin server. It doesn't provide metadata. It asks Jellyfin to rescan a library after LibraryForge changes NFO files, and it reports each user's parental controls.

- **Connection.** Server URL plus an API key (Jellyfin Dashboard → API Keys), sent as `Authorization: MediaBrowser Token="..."`. The URL must be http(s) without credentials, a query, or a fragment. The connection test reads `/System/Info` and shows the server name and version.
- **Library link.** Each library's Jellyfin assignment (Library Settings → Integrations) has a **Jellyfin library** choice, stored in the link's `options.jellyfin_library_id`. LibraryForge suggests one by matching the last folder name of the library's path against each Jellyfin library's folders (so `\\nas\media-library\TVShows` matches `/media/TVShows`), then by library name. The suggestion is only saved when confirmed.
  - `GET /api/integrations/library-links/<id>/jellyfin/` lists Jellyfin's libraries with the selected and suggested link.
  - `POST` with `{"jellyfin_library_id": ...}` saves it; `""` clears it.
- **Rescan.** `POST /api/integrations/library-links/<id>/jellyfin/refresh/` (the **Refresh in Jellyfin** button on the Ratings tab) runs Jellyfin's equivalent of *Scan library* on the linked library: `POST /Items/{id}/Refresh` with `Recursive=true`, `MetadataRefreshMode=Default`, and `ReplaceAllMetadata=false`, so new and changed files (including NFOs) are read and existing metadata isn't replaced. It requires the link to be enabled with the `output` capability.
- **Parental check.** `GET /api/integrations/connections/<id>/jellyfin/parental/` (**Check parental controls** on Settings → Integrations) lists each user's maximum parental rating (named via `/Localization/ParentalRatings` when available), which item types have unrated items blocked, and how many movies and series they can see in total and without a rating. Counts are asked per user, so they reflect that user's own restrictions. A restricted user who can see unrated items of a type that isn't blocked gets a warning. Restricted accounts are listed first.
- **YouTube as TV shows.** For online video libraries, a Channels as TV shows projection builds a hardlinked Jellyfin Shows folder with NFOs and ratings, so Jellyfin doesn't depend on the TubeArchivist plugin. See [JELLYFIN_YOUTUBE_SHOWS.md](JELLYFIN_YOUTUBE_SHOWS.md).
- **Verification.** The header, library list, scan, and user policy fields are confirmed in Jellyfin's OpenAPI spec. Per-library refresh, per-user counts, and rating names follow long-standing Jellyfin API behaviour that the published spec excerpt didn't confirm, so their responses are parsed defensively. A count Jellyfin doesn't return shows as unknown rather than zero.

## Secrets

User-supplied provider secrets are submitted to the Django backend and encrypted before storage. They are never returned to the browser after saving. Encryption is derived from the LibraryForge Django secret key, so `DJANGO_SECRET_KEY` must remain stable for the life of the installation.

Application/project credentials used by future `application` or `hybrid` providers are not ordinary per-user connection fields and should be managed by the provider implementation according to that provider's terms.

## Future providers

The provider registry is intentionally extensible. Planned later milestones can register adapters without redesigning the settings model:

- alpha.5 and later: Fanart.tv and other metadata/artwork providers (TMDB, OMDb, and TheTVDB are implemented).
- alpha.6: Emby, Kodi and other output/server integrations (Jellyfin rescans and parental checks are implemented).

Only implemented providers should appear in the UI.
