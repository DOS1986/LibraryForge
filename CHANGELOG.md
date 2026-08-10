# Changelog

All notable changes to LibraryForge will be documented in this file.

LibraryForge uses Semantic Versioning while the application is under active
pre-1.0 development.

## [Unreleased]

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

### Changed

* Library scans now index recognized local artwork after semantic catalog
  resolution.
* Files browsing and recursive storage totals now include indexed artwork.

### Safety

* Local artwork management is non-destructive.
* LibraryForge does not rename, delete, upload, overwrite, crop, resize, or
  download artwork in this version.
* Artwork reconciliation preserves the existing scan safety rule when
  filesystem discovery encounters errors.


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
