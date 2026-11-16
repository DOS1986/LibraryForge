# Changelog

All notable changes to LibraryForge will be documented in this file.

LibraryForge uses Semantic Versioning while the application is under active
pre-1.0 development.

## [0.1.0-alpha.6] - Unreleased

### Added

* Added a projection engine with stored plans and background runs. Checking a projection builds a plan you review: every change, findings, counts, and a 30-minute expiry. Applying it queues a run of exactly that plan in the background worker, with progress, cancellation, and a per-file journal that records each change before the disk is touched.
* Added run history per projection, with results, problems, and journal details.
* Added movie and TV projections for Jellyfin:
  * Movies go in `Title (Year)` folders with their primary version, a movie NFO, and their selected artwork.
  * Shows go in `Show (Year)` folders with tvshow.nfo, artwork, and `Season 01` folders. Episodes are named `Show S01E02 - Title` with episode NFOs (rated like their show when unrated) and thumbnails.
  * Artwork is copied and refreshed when its source changes. Folder-name clashes get stable ID suffixes.
  * No-file items, multi-episode files, overlong paths, and name collisions are skipped with notes.
  * Plans can be limited to one show.
* Added Emby, Kodi, and generic output profiles for movie and TV projections. They're built to each server's published conventions and labeled as not yet verified on a live server:
  * Every profile uses the same folders and NFOs.
  * Kodi names movie art after the file (`<file>-poster.jpg`, `-clearlogo.png`) and puts season art in the show folder (`season01-poster.jpg`).
  * Emby uses `clearlogo`. Generic projects poster and fanart only.
  * Golden file-list and NFO fixtures in `backend/outputs/golden/` cover each profile.
* Added a media server choice when setting up a projection (`target` on the create endpoint) and a profile switch for existing projections. Changing a projection's profile, folder, media policy, or stale policy replaces its open plans.
* Added `GET/POST /api/libraries/<id>/projections/` for any layout. The Projections page now sets up and runs movie, TV, and online-video folders.
* Added copy and symlink media policies for projections, alongside hardlinks.
* Added NFO and artwork output into the library itself, on the NFO page of movie, TV, and mixed libraries (Sidecar Only and Full Control only). It uses the same reviewed plans, background runs, and history as projections:
  * Missing NFOs are created. Existing NFOs get only the fields LibraryForge has a different value for: other tags, comments, and formatting are kept, and NFO-only values are never erased. A run writes an NFO only if the file is still what the plan read.
  * Each selected image is copied into the item's folder under the chosen media server's names. A different image already there is kept as a `.libraryforge-backup-` file. LibraryForge's own copies are refreshed, or removed once deselected, if unchanged.
  * Read Only libraries are refused when planning and when running. A rerun with no changes writes nothing.

### Changed

* The Channels as TV shows folder now uses the projection engine:
  * Hardlinks need a one-time acknowledgement and are refused for Read Only libraries.
  * Files of deleted videos are removed only after a finished scan with the library reachable, and a "keep them" policy is available.
  * After an interrupted run, files are adopted only where the run journal shows they were being created.
  * Files from alpha.5 are verified against disk once, on the first plan.
* Changed show and episode NFOs to mark the TVDB ID as the default, then TMDB.
* The NFO page's **Create missing NFOs** card is replaced by the NFO and artwork output panel. The `nfo-create` endpoint is unchanged.
* Projection destinations now require `LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS` (development included) and must be separate from every library. Libraries can't be created over a projection's folder.

### Removed

* Removed the template projection engine and its preview and run endpoints, plus the batch `shows-plan` and `shows-sync` endpoints. Existing template projections were converted, turned off, and marked to be previewed.

### Database

* Added migration `outputs.0006_library_nfo_layout`: the `library_nfo` projection layout. Choices only.
* Added migration `outputs.0005_movie_tv_layouts`: `movies` and `tv` layouts, movie-NFO and artwork file kinds, a source fingerprint on managed files, and a group on plan actions. Additive only.
* Added migrations `outputs.0003_projection_plans_and_runs` and `outputs.0004_projection_plan_overview`. They add projection plans, plan actions, runs, and the run journal; stale policy, hardlink acknowledgement, enabled, and preview flags on projections; and ownership and last run on managed files. Existing managed files are marked for verification and template projections are converted. Additive only.

## [0.1.0-alpha.5] - 2026-11-15

### Added

* Added normalized metadata-provider types for movie and series targets: candidates, provider metadata, artwork references, name spaced external IDs, territory-scoped content ratings, and precision-preserving partial dates.
* Added `metadata_target_types` to integration provider definitions and exposed it in the provider catalog API.
* Added `search_metadata`, `get_metadata`, and `supports_metadata_target` to the integration provider contract, with request validation before any network call and validation of adapter output.
* Added stable metadata-provider error categories with explicit retry ability.
* Added registry discovery of providers that support a metadata target type.
* Added contract and compatibility tests confirming YouTube and TubeArchivist keep their known-ID lookups and do not claim movie or series search.
* Added a TMDB integration for movie and TV series metadata retrieval: encrypted API Read Access Token, connection testing, movie and series search, normalized details, certifications and content ratings, IMDb/TVDB/Wikidata IDs, and poster/backdrop/logo references. Retrieval never changes catalog metadata.
* Added TMDB error mapping to stable metadata error categories, one bounded inline retry for transient failures, `Retry-After` handling, and short-lived credential-scoped caching.
* Added TMDB attribution to the provider description and a Credits section on the System page.
* Added mocked TMDB adapter tests covering normalization, malformed and partial responses, error mapping, retries, caching, and credential handling.
* Added read-only metadata matching for movies and series: owner-scoped context, search, and preview endpoints that never change catalog metadata, provenance, or history.
* Added explainable match hints (title, original title, year, external-ID agreement or conflict, possible remakes) with advisory tiers.
* Added a field-level metadata preview that keeps existing and manually edited values by default, suggests only empty fields, blocks locked fields and conflicting IDs, only adds list entries, keeps year and release date consistent, and fingerprints the reviewed state for a later apply step.
* Added a Match tab to the movie and series editor with provider search, candidate selection, comparison, field choices, and provider attribution.
* Added provider attribution to provider definitions and the provider catalog API.
* Added a per-user rate limit for metadata provider requests (`LIBRARYFORGE_METADATA_PROVIDER_RATE`, default `60/min`).
* Added applying reviewed provider metadata to movies and series. The server rebuilds the preview, refuses stale reviews, accepts only selectable field names, keeps year and release date consistent, and writes values, provenance, and history in one transaction.
* Added duplicate-submission protection for provider applies using a client-generated operation ID.
* Added provider provenance: applied fields record the provider as their source with a provider/target/ID reference and are locked against library scans, while a later reviewed match can still replace them and manual edits take priority.
* Added provider change sets to metadata history with the applied fields, previous values, actor, and secret-free apply details.
* Added Apply and confirmation steps to the Match tab, with stale-review recovery.
* Added a library Ratings tab with content-rating coverage for movies and TV series: counts and filters for rated, missing, and unrecognized ratings, title search, and each rating's source.
* Added reviewed rating suggestions: LibraryForge searches the metadata provider for every unrated item on the current page (in sequential batches of 10, with progress and Stop), suggests a rating only for confident matches, and applies each rating only when confirmed, through the validated apply path.
* Added a choice of 25, 50, 100, or 200 items per page on the Ratings tab, remembered in the browser, with first/previous/next/last navigation.
* Added content ratings for online video channels (rated like TV series), and Ratings tabs that show every kind of item a library contains, including mixed libraries.
* Added setting or clearing ratings by hand for selected movies, series, or channels on the Ratings tab, recorded as locked manual edits with history.
* Added a quick rating match from the Ratings tab: Find match opens the item's Match tab with the search already run, each result has Save rating from this match (applies only the rating through the validated apply path), and saving returns to the Ratings list.
* Added estimated US ratings when a provider only has other countries' ratings: each rating is converted to its minimum age (about 20 national systems), the stricter-leaning median is mapped to the US movie or TV scale, and the estimate is labelled, never pre-selected, and saved only on an explicit click.
* Added an OMDb integration for movie and TV series metadata, mainly as a second source of real US ratings (IMDb certifications): API-key connection testing, search, details, defensive parsing of OMDb fields and errors, and short-lived key-scoped caching within OMDb's personal, non-commercial terms.
* Added multi-provider rating suggestions: providers are tried in library priority order, a real rating from any provider wins over an estimate, and IDs found by one provider (such as TMDB's IMDb ID) let the next look the item up directly.
* Added `metadata_id_namespace` to provider definitions so items with a known provider ID are looked up directly.
* Added a TheTVDB v4 integration for TV series and movies: API key plus optional subscriber PIN, month-long login tokens with automatic renewal, search, English translations, country content ratings (two- or three-letter country codes), remote IMDb/TMDB IDs, and direct lookups by the TVDB ID TMDB provides.
* Provider HTTP requests can now send a JSON body (used for TheTVDB login).
* Added editing online videos and channels (title, description, rating, upload date, tags) from the Media page, recorded as locked manual edits with history so scans don't overwrite them. The Jellyfin Shows folder picks up the edits on its next sync.
* Added writing LibraryForge's fields into NFO files from an item's NFO tab (movies, series, episodes). A side-by-side comparison shows each field's status. Only ticked fields change, and every other tag, comment, and formatting in the file is kept. NFO values LibraryForge lacks are never erased, and missing NFOs can be created beside the video or as tvshow.nfo.
* Added Create missing NFOs on the NFO page of movie and TV libraries, which creates NFOs in batches from LibraryForge's metadata for items that have none. See `docs/METADATA_EDITING.md`, which also covers keeping embedded tags out of Jellyfin.
* Added choosing provider artwork in the Match tab: posters, backdrops, logos, banners, and thumbs from TMDB, TheTVDB, or Fanart.tv, shown beside the current artwork. A chosen image is downloaded only from that provider's image host, checked to be a real image, saved beside the item under the name Jellyfin reads (`poster`, `fanart`, `logo`, `banner`, `landscape`), selected, and recorded with provider provenance and history. Existing artwork is replaced only after confirmation and kept as a backup; failures leave the folder unchanged.
* Added a Fanart.tv artwork integration (project key plus optional personal key), looked up by TMDB, IMDb, or TheTVDB ID.
* TMDB artwork now includes smaller thumbnail URLs for browsing choices.
* Added a Channels as TV shows Jellyfin folder for online video libraries (Projections tab): each channel becomes a show with tvshow.nfo, poster, and fanart, each upload year a season, and each video a hardlinked, renamed episode (`S2024E051201 - Title [id].mp4`) with its own NFO and embedded thumbnail. Ratings are written into every NFO. Syncs are previewed, applied in batches (all channels or one), keep episode numbers stable, rename, relink, and remove files as the library changes, and only ever change files LibraryForge recorded writing. TubeArchivist's folder is never changed. See `docs/JELLYFIN_YOUTUBE_SHOWS.md`.
* Added YouTube rating hints for online video channels: the library's YouTube connection reads YouTube's made-for-kids and age-restriction flags for each channel and its most recent videos (up to 250, batched 50 per quota unit), suggests TV-MA for age-restricted content or TV-Y for made-for-kids channels, and applies reviewed hints, recomputed on the server, with provider provenance that never replaces manual ratings.
* Added a Jellyfin server integration: connection test, linking each library to its Jellyfin library (suggested by folder name), a Refresh in Jellyfin rescan after NFO changes that never replaces existing metadata, and a parental-control check showing each user's maximum rating, unrated blocking, and how many movies, series, and unrated items they can see.
* Provider HTTP requests can now use bodiless methods such as POST, and empty responses (HTTP 204) return no data.
* Added a type-or-pick content rating field to the metadata editor, with standard ratings and their meanings narrowing as you type.
* Added importing content ratings from indexed NFO files (`<mpaa>` in movie NFOs and `tvshow.nfo`), with a preview of what will be filled, kept, or disputed. It only fills empty or previously NFO-imported ratings, never replaces manual or provider ratings, links `tvshow.nfo` to series by folder, normalizes Kodi rating spellings, and works for read-only libraries because no files are changed.
* Added writing LibraryForge ratings into existing NFO files (`<mpaa>` in movie NFOs and `tvshow.nfo`) for media-server parental controls, with a preview, batched writes with progress, and per-file results. Only the rating changes; formatting, comments, other tags, and line endings are kept. Files whose content changed since the last scan are skipped, and read-only libraries are never written.
* Added a management mode selector to Library Settings, with confirmation before allowing LibraryForge to change a library's files.
* Added a scan worker heartbeat so LibraryForge knows whether a scan worker is running. The scan panel and Jobs page show when a scan is waiting because no worker is running (with how to start one), when a scan stopped because its worker stopped, and whether the worker is idle or scanning.
* Added cancelling scans: queued and stopped scans end immediately, and running scans stop at their next progress checkpoint, which always comes before files are marked missing.
* Added `run_scan_worker --workers N` (and `LIBRARYFORGE_SCAN_WORKERS`) to scan up to N libraries at once. A supervisor runs N worker processes, restarts crashed workers, drains them on restart requests, and stops them together; workers stop if the supervisor goes away.

### Changed

* Rebranded and redesigned the web interface. A new LibraryForge identity (logo mark, favicon, ember-on-stone "Forge" palette, and type). Light and dark themes that follow the system until you choose, remembered per browser and applied before the page draws. A compact density option for large tables.
* New navigation: a collapsible sidebar with Dashboard, Jobs, each library with its pages (Overview, Media, Files, NFO, Sources, Needs Attention, Ratings, Projections, Settings), and Setup (Integrations, Settings, System). It collapses to icons and slides out on phones. Breadcrumbs and a Ctrl+K / Cmd+K quick search jump to any page, library page, or appearance setting.
* New sign-in page, dashboard (library stats and library cards with quick links), shared page headers, and an Add library dialog. Buttons, cards, inputs, badges, tabs, menus, and dialogs were restyled, so every page uses the new look.
* Page layout pass:
  * Library Overview has stat tiles and a list of the library's pages. Needs Attention is one card.
  * Count tiles, notices, and status badges match everywhere: jobs and health checks are green when done or available, amber when completed with errors.
  * System health checks sit side by side. Settings is a narrower column.
  * Folder browsers show progress while loading.
  * The sidebar keeps only the current library expanded.
* Provider HTTP errors now record a failure reason (timeout, unreachable, invalid JSON, oversized response) and any `Retry-After` delay so adapters can classify failures without parsing messages.
* Integration connection errors from metadata providers now show the provider's sanitized message.
* Metadata history now includes each change set's source reference.
* Writing ratings to NFO files now compares each file's content with the indexed copy instead of its timestamp, so files a media server re-saved without changes can be updated. Files whose content changed are still skipped.

### Fixed

* Writing ratings to NFO files now checks the library folder once before writing and explains why it can't be reached (for example when Windows isn't signed in to the network share), instead of failing every file with a generic message.
* A scan whose worker stopped mid-scan no longer stays "running" forever and blocks new scans of that library. Workers mark such scans as interrupted when they start, and starting a new scan replaces one whose worker is gone.

### Database

* Added migration `outputs.0002_youtube_shows_layout`: a `layout` field on projections and a `ProjectionFile` manifest of files a projection wrote. Additive only.
* Added migration `integrations.0002_library_link_options`: an `options` field on library integration links. Additive only.
* Added migration `catalog.0008_channel_content_rating`: a `content_rating` field on channels. Additive only.
* Added migration `jobs.0004_scan_worker_heartbeat`: a `ScanWorker` heartbeat table, `worker_id` and `cancel_requested` on scan jobs, and a `cancelled` status. Additive only.
* Added migration `catalog.0007_metadata_provider_provenance`: a `provider` source for field provenance and change sets, plus `source_ref`, `operation_id` (unique), and `details` on change sets. Additive only.

## [0.1.0-alpha.4] - 2026-08-11

### Added

* Added first-class Channel, Online Video, Playlist, and Playlist Membership semantic models for online-video libraries.
* Added TubeArchivist and yt-dlp online-video normalization with field provenance and manual-lock preservation.
* Added stable provider/source identities for channels, videos, and playlists.
* Added online-video semantic match, unresolved, and conflict handling using the existing SemanticMatch system.
* Added regression coverage for TubeArchivist precedence, yt-dlp fallback, playlist membership, source conflicts, idempotent rebuilds, and manual metadata locks.
* Added a validated TubeArchivist archive-path identity fallback for online videos when embedded `ta` metadata and yt-dlp `.info.json` are unavailable.
* Added standard embedded title, description, date, artist/channel, and genre fallbacks to online-video canonical metadata while preserving field provenance.
* Added conflict detection between path-derived identities and explicit TubeArchivist/yt-dlp identities.
* Added authenticated read-only online-video catalog APIs for Channels, Playlists, and Videos.
* Added server-side pagination, search, sorting, and Channel/Playlist/provider/kind/date filtering for online-video catalogs.
* Added channel display metadata, playlist membership and position data, present-version details, runtime totals, storage totals, and catalog counts to online-video API responses.
* Added API regression coverage for ownership isolation, present-file filtering, aggregates, relationship serialization, filtering, and malformed query parameters.
* Added first-class Online Video frontend catalog views for Channels, Playlists, and Videos.
* Added Channel and Playlist detail dialogs with paginated video browsing and playlist-position ordering.
* Added Online Video detail views with channel identity, provider/video IDs, tags, categories, playlist memberships, and present physical-version information.
* Added human-readable Channel information to Online Video Media and Files views.
* Added Online Video artwork previews for Channels, Playlists, and Videos.
* Added local adjacent-thumbnail recognition for online videos plus Channel and Playlist artwork association.
* Added indexing and authenticated on-demand preview of embedded attached artwork without writing extracted image files.
* Added preferred artwork URLs and local artwork refresh controls to the Online Video catalog.
* Added a reusable integration framework for metadata, artwork, catalog, and output providers.
* Added global integration management and per-library integration assignments with provider capability and priority configuration.
* Added encrypted server-side storage for user-supplied integration credentials without returning stored secrets to the frontend.
* Added support for credential-free, user-supplied, application-managed, and hybrid integration credential models.
* Added TubeArchivist as an Online Video integration using network-based API access without requiring a shared filesystem or collocated container.
* Added YouTube Data API integration for metadata and artwork enrichment of existing Channels, Playlists, and Videos.
* Added integration connection testing and provider capability/status information.
* Added secure integration-provided artwork proxying with provider fallback and origin validation.
* Added batched Online Video provider lookups and short-lived caching to reduce external metadata API requests.
* Added public integration architecture documentation for current and future LibraryForge providers.
* Added mixed-library Online Video catalog browsing with separate Movies & TV and Online Video catalog views.
* Added regression coverage for mixed-library Online Video routing, conservative embedded-metadata classification, mixed-library automatic reset, stale identity reuse, primary-version replacement, and true duplicate conflicts.
* Added mixed-library Online Video catalog browsing with separate Movies & TV and Online Video catalog views.
* Added regression coverage for mixed-library Online Video routing, conservative embedded-metadata classification, mixed-library automatic reset, stale identity reuse, primary-version replacement, and true duplicate conflicts.

### Changed

* Online Video libraries now build a semantic catalog from already-indexed TubeArchivist and yt-dlp metadata during the normal scan semantic-resolution stage.
* Online Video libraries now default the Media page to the semantic Catalog view.
* TubeArchivist `UC...` root folders now display their resolved Channel name while retaining the original physical folder ID and path.
* Media and unified file APIs now expose Channel identity/display fields for Online Video media.
* Online Video Channel, Playlist, Video, and related-video views now display preferred artwork when available.
* Virtual embedded artwork is excluded from physical Files listings and physical file/storage totals.
* Automatic artwork selection prefers filesystem sidecars over embedded artwork when no preferred selection already exists.
* Online Video artwork can now fall back to assigned integrations when local or embedded artwork is unavailable.
* TubeArchivist enrichment no longer assumes LibraryForge and TubeArchivist share a filesystem namespace.
* Integration providers now declare their credential ownership model instead of assuming all external services require user-supplied credentials.
* Application-managed integration credentials are resolved only on the server and are not stored in per-user connection configuration.
* The integration provider registry remains code-driven so future providers can be added without database schema changes solely to register a provider.
* LibraryForge integrations are explicitly limited to metadata, artwork, catalog, and output capabilities; media acquisition and download automation remain outside the product scope.
* Mixed libraries now route only files with explicit Online Video signals through the Online Video semantic resolver.
* Online Video semantic resolution now reuses an existing absent semantic item when a replacement file has the same stable provider/video identity.
* Present replacement files can become the primary MediaVersion when the previous primary file is no longer present.
* Integration API errors now suppress raw non-JSON server HTML and surface a concise HTTP failure message instead.
* Mixed libraries now route only files with explicit Online Video signals through the Online Video semantic resolver.
* Online Video semantic resolution now reuses an existing absent semantic item when a replacement file has the same stable provider/video identity.
* Present replacement files can become the primary MediaVersion when the previous primary file is no longer present.
* Integration API errors now suppress raw non-JSON server HTML and surface a concise HTTP failure message instead.

### Fixed

* Fixed false `duplicate_source_identity` conflicts when a moved or replacement Online Video file reappears with the same provider/video ID after the previous physical file is absent.
* Fixed Reset to Automatic routing for Online Video matches stored inside mixed libraries.
* Fixed mixed-library Online Video records being semantically classified without a corresponding Online Video catalog view.
* Fixed raw Django HTML error pages being rendered directly in the Integrations UI.
* Fixed false `duplicate_source_identity` conflicts when a moved or replacement Online Video file reappears with the same provider/video ID after the previous physical file is absent.
* Fixed Reset to Automatic routing for Online Video matches stored inside mixed libraries.
* Fixed mixed-library Online Video records being semantically classified without a corresponding Online Video catalog view.
* Fixed raw Django HTML error pages being rendered directly in the Integrations UI.

## [0.1.0-alpha.3] - Artwork Management and Application Housekeeping

### Added

* First-class local artwork indexing for Movies, Series, Seasons, and Episodes.
* Detection of common local artwork conventions including poster, folder, cover, fanart, backdrop, banner, logo, clear logo, landscape, thumb, and episode thumbnail files.
* Artwork association with semantic catalog entities after semantic resolution.
* Authenticated artwork preview endpoints.
* Preferred-artwork selection without modifying the source image files.
* Artwork tab in the canonical catalog editor.
* Local artwork refresh without requiring a full media or ffprobe scan.
* Artwork records in the Files browser, recursive file counts, and storage totals.
* Regression tests for artwork discovery, association, selection, API access, and scan behavior.
* Persistent per-user application settings through `UserSettings`.
* Configurable default page size and Needs Attention sorting preferences.
* User display-name and build-information visibility preferences.
* Initials-based user avatar and account dropdown.
* Global Settings page.
* System Status page with application and dependency information.
* Public system health endpoint.
* Staff and superuser application restart controls.
* Restart audit history through `SystemAction`.
* Cross-platform development supervisors now manage the Django server, scan worker, and Vite frontend as one LibraryForge development stack.
* macOS Finder-compatible development launcher.
* Restart/startup splash screen with health polling and automatic return to the login page.
* Regression tests for user preferences, health checks, restart authorization,
  and supervisor restart requests.

### Changed

* Library scans now index recognized local artwork after semantic catalog resolution.
* Files browsing and recursive storage totals now include indexed artwork.
* Needs Attention queues now support server-side sorting with sortable table headers.
* Needs Attention sorting preferences persist per user.
* The header email and standalone Sign Out button have been replaced by an account menu containing Settings, System Status Restart LibraryForge, and Log Out.
* Build information can now be shown or hidden through the user's settings.
* Application restart now waits for an active scan to finish before restarting the scan worker, preventing in-progress scan jobs from being abandoned.
* Queued scan jobs remain queued across application restarts and are processed by the newly started worker.
* Added Online Video support to Needs Attention with TubeArchivist, yt-dlp, TubeArchivist-path, suggested, and manual identity remediation workflows.
* Added semantic provenance inspection for current Online Video identity, canonical field sources, indexed metadata sources, playlist memberships, confidence, and lock state.
* Added manual Online Video provider/video/channel identity correction with validation, notes, lock controls, canonical field provenance, and metadata change history.
* Added Online Video semantic rebuild support to `rebuild_semantic_catalog --all` using already-indexed metadata.
* Added regression coverage for Online Video manual resolution, source-candidate confirmation, lock synchronization, automatic reset, provenance, shared Channel safety, and canonical-title preservation.

### Safety

* Local artwork management is non-destructive.
* LibraryForge does not rename, delete, upload, overwrite, crop, resize, or download artwork in this version.
* Artwork reconciliation preserves the existing scan safety rule when filesystem discovery encounters errors.
* Application restart is restricted to staff and superuser accounts.
* Restart requests do not expose arbitrary operating-system commands through the web API.
* Only the administrator requesting a restart is logged out; other user sessions are preserved.
* Reset to Automatic now routes Online Video libraries through the Online Video semantic resolver instead of the Movie/TV resolver.
* Confirming detected Online Video identity candidates now changes semantic identity only and leaves source-provided descriptive metadata under the canonical metadata/provenance system.
* Manual Channel reassignment now preserves shared Channel identities used by other videos and reassigns only the remediated video.
Commit

## [0.1.0-alpha.2] - Canonical Metadata Editor

### Added

* Canonical metadata editor for Movies, Series, Seasons, and Episodes.
* Explicit canonical fields for sort/original title, tagline, content rating,
  genres, studios, and external IDs.
* Field-level provenance and manual override locking through
  `CanonicalFieldState`.
* Canonical metadata change history through `MetadataChangeSet`.
* Editable MediaVersion name, edition, notes, and primary-version selection.
* Contextual source inspection for filename, ffprobe, embedded, NFO,
  TubeArchivist, and yt-dlp metadata already indexed by LibraryForge.
* Contextual NFO validation and editing from Movie and Episode catalog items.
* Catalog editor API endpoints for Movies, Series, Seasons, Episodes, and
  MediaVersions.
* Regression tests for manual metadata persistence, resolver protection,
  version overrides, history, and catalog-editor API behavior.

### Changed

* Semantic scans now preserve manually overridden canonical fields instead of replacing them on a later scan.
* Semantic scans record automatic provenance for core identity and display fields such as Movie title/year, Series title/year and Episode title.
* MediaVersion semantic refreshes preserve manually edited names and editions.
* Movie and TV catalog browsing now opens the canonical metadata editor instead of the earlier read-only Movie/version dialog or generic Episode detail dialog.

### Safety

* Canonical display-metadata edits do not rewrite `semantic_key` values.
  Identity corrections remain an explicit Needs Attention/re-identification
  workflow.
* Exactly one MediaVersion may be primary for a MediaItem at the database level.

## [0.1.0-alpha.1] - Development Baseline

### Added

* PostgreSQL-backed media libraries and scan jobs.
* Physical folder, media file, NFO, and metadata-source browsing.
* Server-side pagination, sorting, recursive folder totals, and storage totals.
* NFO parsing, editing, validation, and projection support.
* Semantic Movie and TV catalog models.
* Series, Season, Episode, Movie, and MediaVersion relationships.
* Semantic matching from folders, filenames, and NFO metadata.
* Needs Attention queues for unresolved and conflicting semantic metadata.
* Manual semantic resolution, confirmation, locking, and automatic reset.
* Semantic normalization for filesystem-safe title differences.
* Numeric media-title handling for titles such as 1917, 1923, and 2067.

### Notes

This version established the initial semantic media catalog and conflict
resolution foundation for LibraryForge.
