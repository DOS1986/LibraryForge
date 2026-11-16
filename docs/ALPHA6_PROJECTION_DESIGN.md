# 0.1.0-alpha.6 — Projection and Output Engine (design)

Status: approved 16 November 2026. Phases 1 to 5 implemented (see PROJECTIONS.md); Jellyfin live verification is pending.

This design adapts the reconstructed "LibraryForge Projection and Output Engine" document (ChatGPT, 16 November 2026) to how LibraryForge is used today and to an alpha-sized scope. Where this document differs from that one, this one is the plan, and the reason is given.

## 1. Goal

Turn LibraryForge's canonical catalog into safe, repeatable outputs that Jellyfin, Emby, Kodi, and generic consumers read:

* **Projections:** separate output folders (hardlinked or copied media, NFOs, artwork) for movie, TV, and online-video libraries.
* **Library NFO output:** complete NFOs and artwork written beside the originals in Sidecar Only and Full Control libraries.

Both are planned, previewed, applied as recorded runs, and repeatable: an unchanged rerun writes nothing.

## 2. Decisions

| # | Decision | Differs from the source design? |
| --- | --- | --- |
| D1 | One engine for every projection. The old template engine is retired; its projections become generic-profile projections previewed before their first sync. | No |
| D2 | **Hardlinks** are allowed in Sidecar Only and Full Control after a one-time acknowledgement per projection. They're blocked in Read Only. The default is hardlink when the destination is on the same volume, otherwise copy, shown in the preview, never a silent fallback. | Yes: the source design blocks hardlinks outside Full Control and defaults to copies. Copies would double multi-terabyte libraries, and the existing YouTube Shows folder (Sidecar Only) depends on hardlinks. Media servers write NFOs and images beside media, not into it. |
| D3 | **Stale output** (its source is gone, or it's no longer selected) is removed by default, if LibraryForge created it and it's unchanged. No removal is proposed when the library's last scan was incomplete or errored, when the share is unreachable, or for objects outside a scoped plan. A "keep and report" policy is available per projection. | Yes: the source design keeps stale output by default. Kept hardlinks to deleted videos never free disk space. |
| D4 | Projection output folders can't be libraries, and libraries can't be created over them. The existing "Youtube Shows" library is removed (its catalog records only; no files are touched). | No (the source design requires it) |
| D5 | **Library NFO output** writes in place through the alpha.5 NFO writer (Sidecar Only and Full Control only). It shares the serializers and profiles with projections but is a separate workflow with its own write path. | Yes: the source design leaves source sidecar writes out of alpha.6. |
| D6 | Output roots come from `LIBRARYFORGE_ALLOWED_OUTPUT_ROOTS` and are required for every user, DEBUG included. A projection's destination may not contain, or sit inside, any library folder (a root itself may be a shared parent). | No |
| D7 | Emby and Kodi are built to their published conventions and labeled "not verified on a live server". Jellyfin is verified on the maintainer's server. | Yes: the source design asks for a tested compatibility matrix. |
| D8 | Trimmed scope (section 12). | Yes |

## 3. Architecture

```text
catalog (canonical values, selected artwork, field provenance)
        |
  snapshot builder ── profile + layout ──> desired artifacts (paths, NFO bytes, art, links)
        |                                          |
        |                       manifest (ProjectionFile) + observed destination
        |                                          |
        └──────────────────────────────> planner + validators
                                                   |
                                     ProjectionPlan (stored, digest, expiry)
                                                   |
                                     user reviews preview → approves
                                                   |
                                     ProjectionRun (background job)
                                                   |
                                     executor: per-action recheck, journal, write
                                                   |
                                     manifest + run history (+ optional Jellyfin refresh)
```

Services live in `outputs/services/`: `snapshot`, `layouts` (movies, tv, online_video), `profiles` (jellyfin, emby, kodi, generic), `planner`, `executor`, `nfo` (shared serializers, extracted from `youtube_shows.py` and `metadata/services/nfo_fields.py`). The existing integrations registry provides Jellyfin refresh; profiles are not integration providers and need no connection.

## 4. Data model (additive migrations)

* **OutputProfile**: add `revision`, `options` (JSON, validated per target: naming, NFO fields, artwork names). `nfo_root_element` becomes derived and deprecated.
* **Projection**: `layout` becomes `movies | tv | online_video` (the old `template` maps to generic). Add `stale_policy` (`remove_owned` default, `keep`), `hardlink_acknowledged`, `selection` (all, or chosen object IDs), `enabled`, `revision`, `needs_preview`, `last_successful_run`. `link_mode` defaults to `hardlink`.
* **ProjectionPlan**: projection, requested_by, status (`building, ready, blocked, expired, superseded, applied`), configuration and catalog revision digests, `content_digest`, counts, findings, `created_at`, `expires_at` (30 minutes by default, configurable).
* **ProjectionPlanAction**: plan, ordinal, kind (`create, update, relink, replace, remove, unchanged, conflict`), artifact kind, object and source IDs, relative path, comparison key, expected-before evidence (hash, size, file identity), desired-after (NFO bytes stored inline, link source, or artwork source and hash), reason, severity.
* **ProjectionRun**: plan, actor, worker, status (`queued, running, succeeded, completed_with_errors, failed, cancelled, interrupted`), idempotency key (unique per projection), counts, timestamps, heartbeat, cancel flag.
* **ProjectionRunAction**: run, plan action, state (`intent, done, skipped, failed`), evidence, message. Intent is written before each filesystem change.
* **ProjectionFile** (the manifest): add `comparison_key`, `source_identity` (device and file ID where available, size, mtime), `link_mode`, `ownership` (`owned, legacy_verified, drift`), `last_run_action`.

Deleting a projection, profile, or library never deletes output and never cascades away run history (`SET_NULL` plus copied identifiers).

## 5. Layouts and profiles

| | Jellyfin | Emby | Kodi | Generic |
| --- | --- | --- | --- | --- |
| Movie folder | `Title (Year)/Title (Year).ext` | same | same | same |
| Movie NFO | `<basename>.nfo` | `<basename>.nfo` | `<basename>.nfo` | `<basename>.nfo` |
| Series / season | `Show (Year)/Season 01/` | same | same | same |
| Episode file | `Show S01E02 - Title.ext` | same | same | same |
| Show NFO | `tvshow.nfo` | `tvshow.nfo` | `tvshow.nfo` | `tvshow.nfo` |
| Movie / show art | `poster`, `fanart`, `logo`, `banner`, `landscape` | `poster`, `fanart`, `clearlogo`, `banner`, `landscape` | movies `<basename>-poster`, `-fanart`, `-clearlogo`, `-banner`, `-landscape`; shows without the prefix | `poster`, `fanart` |
| Season art | `Season 01/poster` | `Season 01/poster` | show folder `season01-poster`, `season-specials-poster` | `Season 01/poster` |
| Episode thumb | `<basename>-thumb` | `<basename>-thumb` | `<basename>-thumb` | `<basename>-thumb` |
| Online video | existing Channels as TV shows layout | same | same | same |

Exact Emby and Kodi names are checked against their documentation before phase 3 (section 11). NFOs are complete, deterministic outputs (stable element order, no timestamps), with typed `<uniqueid>` values for known namespaces only. Multi-episode files, disc folders, stacked parts, and extras are blocked with a reason.

## 6. Media policies and management modes

| Operation | Read Only | Sidecar Only | Full Control |
| --- | --- | --- | --- |
| Copy media to an output root | Allowed | Allowed | Allowed |
| Hardlink media to an output root | Blocked | Allowed after acknowledgement | Allowed after acknowledgement |
| Symlink media to an output root | Allowed where the platform supports it | same | same |
| NFOs and artwork in an output root | Allowed (always copies) | Allowed | Allowed |
| Library NFO output (in place) | Blocked | Allowed | Allowed |
| Rename, move, or delete source media | Blocked | Blocked | Blocked (alpha.7) |

The planner, run acceptance, and executor enforce these, not just the UI. A library switched to a stricter mode invalidates pending plans. The acknowledgement explains that a hardlink is the same file under a second name, so nothing should write into the media through the output folder.

## 7. Safety rules

* **Destination checks.** Every destination path is joined only through the validated root, confined after directories are created, and checked for links or junctions that leave the root. Absolute, traversal, reserved-name, trailing-dot, and overlong paths are rejected.
* **Collisions.** These are checked among desired artifacts, the manifest, and files already on disk, by a comparison key that folds case and Unicode form.
* **Foreign files.** These are never replaced or adopted by name or content.
* **Changed owned files.** A changed owned NFO or image is drift: it's reported and left alone until you choose to overwrite it in a cleanup review, which keeps the changed file as a backup.
* **Before each change.** The executor rechecks the root, the expected-before evidence, and the source identity before each action.
* **Media replacement.** Media is never written through an existing link. Replacements unlink the owned entry and create a new one.
* **Write mechanics.** Copies are written to a temporary file in the destination folder, verified by hash, then renamed into place. Generated files are written atomically.
* **Writers.** There's one writer per output root, enforced by a database row lock held by the single projection worker.
* **Removal guards (D3).** Removals require a complete last scan of the library with no traversal errors, a reachable share, and an in-scope object.

## 8. Plans, runs, and recovery

1. **Build a plan.** Building a plan reads only. It creates no folders, links, thumbnails, or network requests.
2. **Review.** The preview shows every action, filterable and paginated over the complete plan. Blocking findings disable apply.
3. **Apply.** Applying sends the plan ID, digest, and an idempotency key. A changed catalog, configuration, mode, or managed file makes the plan stale and asks for a new preview.
4. **Run in the background.** Runs execute in the background worker (`run_scan_worker` gains projection jobs; the scan behavior is unchanged), action by action, with progress and cancellation between actions.
5. **Recover.** After a crash, the journal shows which actions had intent without completion. Recovery checks each one against disk (same file as the source for links, hash for generated files) before recording it or redoing it. Unexplained files are left alone.
6. **Check for no changes.** A rerun after a successful run plans zero writes.

## 9. Library NFO output (in place)

A library-level workflow on the NFO page, for Sidecar Only and Full Control libraries:

* **Choose a profile.** It sets the NFO dialect and artwork names.
* **Preview.** For each item, it shows create (no NFO), update (fields that differ), or unchanged, using the alpha.5 field-level writer: only chosen fields change, other tags are kept, and NFO-only values are never erased.
* **Artwork.** Copy the selected artwork into the item's folder under the profile's names, keeping existing art as backups like alpha.5's artwork save.
* **Apply.** It runs as a background run with the same history UI.

## 10. API (under the existing `/api/` prefix)

| Route | Behavior |
| --- | --- |
| `GET/POST /output-profiles/`, `GET/PATCH /output-profiles/{id}/` | Profiles with validated options |
| `GET /output-roots/` | The configured roots the server allows |
| `GET/POST /projections/`, `PATCH /projections/{id}/` | Projection configuration; never touches disk |
| `POST /projections/{id}/plans/` | Build a plan (background for large libraries) |
| `GET /projection-plans/{id}/`, `GET /projection-plans/{id}/actions/` | Plan status, findings, and paginated actions |
| `POST /projection-plans/{id}/runs/` | Apply an approved plan (digest and idempotency key) |
| `GET /projection-runs/{id}/`, `/actions/`, `POST /cancel/` | Run progress, journal, and cancellation |
| `POST /libraries/{id}/projections/` with `layout: library_nfo` | Library NFO output: a projection with no output folder, so its plans and runs use the projection routes above |
| `POST /projections/{id}/plans/` with `cleanup: true` | A cleanup review: kept files to remove, missing owned files to restore, changed owned NFOs and images to overwrite with a backup |
| `GET /outputs/` | The Outputs page: every projection's state, the output roots, and recent runs |

The alpha.5 `shows-plan` and `shows-sync` routes and the template `preview` and `run` routes are removed together with the frontend change.

## 11. Migration

* Existing profiles and projections keep their IDs. Template projections become generic-profile projections marked `needs_preview`.
* Existing Shows manifest entries are verified automatically: a link must be the same file as its source, and an NFO's or image's hash must match. Verified entries become `legacy_verified`; anything else becomes a conflict for review. Episode numbers are preserved.
* The "Youtube Shows" library is removed after confirmation. It's then blocked by D4.
* No migration copies, renames, or deletes files.
* Emby's and Kodi's conventions were verified before phase 3 and are recorded in section 5 and in `outputs/services/profiles.py`:
  * Emby: its Movie Naming and TV Naming support articles.
  * Kodi: its scanner source, `ART::AddLocalItemArtwork` and `CVideoInfoScannerArt::GetSeasonThumbs` in xbmc/xbmc. The wiki refused automated reads.
  * Emby's NFO article wasn't found. Emby reads Kodi-style NFOs, and that's unverified until it's tried on a live server.

## 12. Deferred (not in alpha.6)

Fencing tokens and cross-host locks, a content-addressed snapshot store, an `OutputRoot` table, a quarantine subtree and timed purge, a player compatibility matrix, performance benchmarks, conditional symlink exposure verification, non-TV generic schemas, `metadata.json` exports, and remote refresh for Emby and Kodi.

## 13. Phases and acceptance

1. **Unified engine:**
   * models, planner, executor, journal, and background runs
   * online-video layout on the new engine, Shows migration, and removal of the old engine and the "Youtube Shows" library
   * Accepted when your Shows folder previews as no changes after migration, and a rerun writes nothing.
2. **Movies and TV:**
   * layouts, Jellyfin profile, artwork copies, collision and validation findings
   * Accepted when a movie and a TV fixture library project and rerun with no changes, and foreign files and drift survive.
3. **Emby, Kodi, and generic profiles:**
   * built on the verified conventions
   * Accepted when golden NFO and naming fixtures exist per profile.
4. **Library NFO output:**
   * in-place create and update with profile artwork names
   * Accepted when Read Only is refused and a no-change rerun writes nothing.
5. **History and UI:**
   * Outputs page, plan preview, run progress and history, cleanup review, and docs
   * Accepted when the full suite and build pass, the changelog is updated, and Jellyfin is verified live.
