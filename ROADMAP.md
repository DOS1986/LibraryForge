# LibraryForge Roadmap

LibraryForge is a self-hosted media metadata manager, editor, organizer, and projection engine.

This roadmap tracks the major product milestones leading from the current pre-release builds toward the first stable `1.0.0` release. Detailed implementation work belongs in GitHub Issues and is grouped by milestone.

## Release progression

LibraryForge uses Semantic Versioning with explicit pre-release stages:

```text
0.1.0-alpha.N
    ↓
0.1.0-beta.N
    ↓
0.1.0-rc.N
    ↓
1.0.0
```

LibraryForge will **not** publish a plain `0.1.0` as the stable product release. While the major version remains `0`, the project is still considered initial development. `1.0.0` is the point where LibraryForge declares its supported product contract, upgrade path, data model expectations, and normal operating behavior stable.

- **Alpha** — major capabilities and architecture are still being built and may change.
- **Beta** — the core feature set is complete enough for full-system real-world testing; work focuses on bugs, edge cases, UX, performance, installation, upgrades, and security.
- **Release Candidate (RC)** — feature work is frozen. A release candidate should become `1.0.0` unless release-blocking defects are discovered.
- **1.0.0** — first stable release with a supported installation, upgrade, data-integrity, and operational contract.

Additional beta and RC builds are created as needed; their exact count is intentionally not predetermined.

## Current status

### 0.1.0-alpha.1 — Semantic Catalog Foundation

Completed.

- PostgreSQL-backed libraries and scan jobs
- Movie and TV semantic catalog
- Series, Season, Episode, and MediaVersion relationships
- semantic matching from filename, folder, and NFO sources
- Needs Attention queues
- manual conflict resolution and locking
- semantic normalization and numeric-title handling

### 0.1.0-alpha.2 — Canonical Metadata Editor

Completed.

- canonical Movie, Series, Season, and Episode metadata editing
- field-level provenance and manual override locking
- metadata change history
- MediaVersion editing and primary-version selection
- source inspection
- contextual NFO editing
- semantic identity kept separate from display metadata

### 0.1.0-alpha.3 — Artwork and Application Housekeeping

Completed.

- local artwork detection, indexing, preview, and preferred-art selection
- artwork integration with Movies, Series, Seasons, and Episodes
- artwork included in physical file browsing and storage totals
- Needs Attention server-side sorting
- persistent per-user settings
- account/avatar menu
- system status and health endpoints
- controlled application restart
- Windows, Linux, and macOS development supervisors
- coordinated Django, scan-worker, and Vite restart behavior

### 0.1.0-alpha.4 — Online Video / TubeArchivist Catalog

Goal: make `online_video` a first-class LibraryForge media domain without forcing online video into Movie/TV semantics.

Completed.

- OnlineVideo / Video semantic model
- Channel model and channel catalog
- Playlist model and playlist membership
- parse TubeArchivist metadata embedded in archived media
- normalize yt-dlp metadata already available in source files/sidecars
- canonical Video metadata editor
- Channel → Videos browsing
- Playlist → Videos browsing
- online-video source/provenance inspection
- online-video thumbnail/artwork association
- preserve TubeArchivist source files without rename/move operations
- regression tests for online-video identity and metadata persistence

## Planned alpha milestones

### 0.1.0-alpha.5 — Metadata Providers

Goal: enrich canonical metadata through optional external providers without making provider data the source of truth.

Planned work:

- metadata-provider abstraction
- provider settings and credentials
- TMDb Movie and TV integration
- search and candidate matching
- preview changes before applying provider metadata
- field-level merge decisions
- provider provenance
- provider artwork discovery hooks
- external ID management
- provider failure/rate-limit handling
- no automatic destructive metadata replacement

Additional providers can be added after the provider abstraction is proven.

### 0.1.0-alpha.6 — Projection and Output Engine

Goal: turn canonical LibraryForge metadata into safe target-specific projections.

Planned work:

- mature OutputProfile model
- Jellyfin output profile
- Emby output profile
- Kodi output profile
- generic NFO/filesystem profile
- dry-run projection preview
- NFO generation from canonical metadata
- artwork projection
- symlink/hardlink/copy projection policies
- collision detection
- output validation
- projection history

Source media remains protected according to each library's management mode.

### 0.1.0-alpha.7 — Safe Library Operations

Goal: add intentional, reviewable filesystem-changing workflows for Full Control libraries.

Planned work:

- ChangeSet model and operation planning
- bulk canonical metadata editing
- rename planning
- move planning
- sidecar rename/move operations
- artwork upload/rename/delete workflows
- operation preview
- collision detection
- rollback/undo where technically possible
- destructive-operation confirmation
- audit trail
- management-mode enforcement

No operation should mutate files before the user can inspect the planned changes.

### 0.1.0-alpha.8 — Reliability and Deployment

Goal: make LibraryForge resilient enough for long-running self-hosted use.

Planned work:

- interrupted scan-job recovery
- worker crash recovery
- stale-job detection
- structured application logging
- production systemd service definitions
- macOS launchd support
- Windows service support
- Docker production deployment path
- database backup/restore guidance
- diagnostics bundle
- health/readiness checks
- upgrade and migration validation
- storage outage/recovery behavior

## Beta phase

### 0.1.0-beta.1 — Full-System Beta

Goal: validate LibraryForge as a complete product rather than a collection of subsystems.

Expected focus:

- fresh-install onboarding
- production deployment documentation
- upgrade testing
- multi-user behavior review
- permission/security review
- performance testing with large libraries
- scan/rescan reliability testing
- provider and projection integration testing
- backup/restore testing
- accessibility and responsive UI review
- end-user documentation
- beta feedback and issue triage

### 0.1.0-beta.N — Additional Beta Cycles

Additional beta builds will be created whenever beta testing finds work that should be validated before a release candidate.

Beta builds should focus on:

- bugs and regressions
- data-integrity issues
- difficult media-library edge cases
- installation and upgrade problems
- performance and scalability
- UX inconsistencies
- security findings
- documentation gaps

Large new core subsystems should normally be deferred unless testing demonstrates they are required for the 1.0 product contract.

## Release-candidate phase

### 0.1.0-rc.1 — First 1.0 Release Candidate

Goal: produce the first build that LibraryForge believes can become `1.0.0` unchanged except for version promotion.

Release-candidate rules:

- feature freeze
- no new major subsystems
- no speculative refactors
- release-blocking defects only
- fresh-install validation
- supported-upgrade validation
- migration validation
- backup/restore validation
- deployment validation on supported platforms
- security review
- final documentation review

### 0.1.0-rc.N — Additional Release Candidates

If an RC uncovers a release blocker, fix it and produce another RC. Repeat until an RC passes the release criteria.

## 1.0.0 — First Stable Release

LibraryForge reaches `1.0.0` when the latest release candidate satisfies the stable-release criteria.

Target characteristics:

- stable supported installation path
- documented upgrade policy
- documented supported platforms/deployment methods
- mature Movie, TV, and Online Video workflows
- reliable canonical metadata management
- provider enrichment
- safe projection/output workflows
- reliable background jobs and recovery behavior
- security and privacy documentation
- tested backup and recovery
- stable database migrations and versioning expectations
- documented management-mode safety guarantees
- no known release-blocking data-loss, security, or upgrade defects

After `1.0.0`, normal Semantic Versioning applies:

- `1.0.1` — backwards-compatible bug fixes
- `1.1.0` — backwards-compatible functionality
- `2.0.0` — intentional breaking changes to the stable contract

## Guiding principles

1. Canonical metadata belongs to LibraryForge, not to any one player or metadata provider.
2. Semantic identity and display metadata are separate concerns.
3. Source provenance must remain visible.
4. Manual user decisions must survive automatic rescans.
5. Read Only means no source filesystem writes.
6. Sidecar Only means source media remains untouched.
7. Full Control operations must be explicit, previewable, and auditable.
8. Scans must never mark records missing when filesystem traversal is incomplete or errored.
9. External providers are optional enrichment sources, not mandatory runtime dependencies.
10. No media re-encoding solely for metadata management.
11. Beta begins only after the intended 1.0 core subsystems exist.
12. Release candidates are feature-frozen builds intended to become 1.0.
