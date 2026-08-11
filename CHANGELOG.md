# Changelog

All notable changes to LibraryForge will be documented in this file.

LibraryForge uses Semantic Versioning while the application is under active
pre-1.0 development.

## [Unreleased]

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
* Added TubeArchivist as an Online Video integration using network-based API access without requiring a shared filesystem or colocated container.
* Added YouTube Data API integration for metadata and artwork enrichment of existing Channels, Playlists, and Videos.
* Added integration connection testing and provider capability/status information.
* Added secure integration-provided artwork proxying with provider fallback and origin validation.
* Added batched Online Video provider lookups and short-lived caching to reduce external metadata API requests.
* Added public integration architecture documentation for current and future LibraryForge providers.

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


## [0.1.0-alpha.3] - Artwork Management and Application Housekeeping

### Added

* First-class local artwork indexing for Movies, Series, Seasons, and Episodes.
* Detection of common local artwork conventions including poster, folder, cover,
  fanart, backdrop, banner, logo, clearlogo, landscape, thumb, and episode
  thumbnail files.
* Artwork association with semantic catalog entities after semantic resolution.
* Authenticated artwork preview endpoints.
* Preferred-artwork selection without modifying the source image files.
* Artwork tab in the canonical catalog editor.
* Local artwork refresh without requiring a full media or ffprobe scan.
* Artwork records in the Files browser, recursive file counts, and storage
  totals.
* Regression tests for artwork discovery, association, selection, API access,
  and scan behavior.
* Persistent per-user application settings through `UserSettings`.
* Configurable default page size and Needs Attention sorting preferences.
* User display-name and build-information visibility preferences.
* Initials-based user avatar and account dropdown.
* Global Settings page.
* System Status page with application and dependency information.
* Public system health endpoint.
* Staff and superuser application restart controls.
* Restart audit history through `SystemAction`.
* Cross-platform development supervisors now manage the Django server, scan
  worker, and Vite frontend as one LibraryForge development stack.
* macOS Finder-compatible development launcher.
* Restart/startup splash screen with health polling and automatic return to the login page.
* Regression tests for user preferences, health checks, restart authorization,
  and supervisor restart requests.

### Changed

* Library scans now index recognized local artwork after semantic catalog
  resolution.
* Files browsing and recursive storage totals now include indexed artwork.
* Needs Attention queues now support server-side sorting with sortable table
  headers.
* Needs Attention sorting preferences persist per user.
* The header email and standalone Sign Out button have been replaced by an
  account menu containing Settings, System Status, Restart LibraryForge, and
  Log Out.
* Build information can now be shown or hidden through the user's settings.
* Application restart now waits for an active scan to finish before restarting
  the scan worker, preventing in-progress scan jobs from being abandoned.
* Queued scan jobs remain queued across application restarts and are processed
  by the newly started worker.

### Safety

* Local artwork management is non-destructive.
* LibraryForge does not rename, delete, upload, overwrite, crop, resize, or
  download artwork in this version.
* Artwork reconciliation preserves the existing scan safety rule when
  filesystem discovery encounters errors.
* Application restart is restricted to staff and superuser accounts.
* Restart requests do not expose arbitrary operating-system commands through
  the web API.
* Only the administrator requesting a restart is logged out; other user
  sessions are preserved.


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

* Semantic scans now preserve manually overridden canonical fields instead of
  replacing them on a later scan.
* Semantic scans record automatic provenance for core identity and display
  fields such as Movie title/year, Series title/year, and Episode title.
* MediaVersion semantic refreshes preserve manually edited names and editions.
* Movie and TV catalog browsing now opens the canonical metadata editor instead
  of the earlier read-only Movie/version dialog or generic Episode detail
  dialog.

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
