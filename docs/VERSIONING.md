# LibraryForge Versioning

LibraryForge uses one product version across the entire application.

The authoritative version is stored at the repository root:

```text
VERSION
```

Example:

```text
0.1.0-alpha.3
```

Do not independently invent frontend and backend product versions.

For release-stage policy and promotion criteria, see:

```text
docs/RELEASE_STRATEGY.md
```

---

## Version Sources

The version manager synchronizes:

```text
VERSION
        │
        ├── backend/pyproject.toml
        │
        └── frontend/package.json
```

The frontend additionally receives generated build identity:

```text
frontend/public/build-info.json
```

That generated file contains:

```json
{
  "name": "LibraryForge",
  "version": "0.1.0-alpha.3",
  "git_sha": "...",
  "git_short_sha": "...",
  "git_branch": "main",
  "git_dirty": false,
  "build_time": "..."
}
```

`build-info.json` is generated automatically before normal Vite development
and production builds and is ignored by Git.

The Django backend reads `VERSION` directly and exposes:

```text
GET /api/system/version/
```

The authenticated application UI compares the frontend and backend build
identities and reports `Synced` or `Mismatch`.

---

## First-Time Setup

From the repository root:

```powershell
python scripts/version.py install
```

This:

1. Reads `VERSION`.
2. Updates `backend/pyproject.toml`.
3. Updates `frontend/package.json`.
4. Adds npm `predev` and `prebuild` hooks.
5. Adds generated build metadata to `.gitignore`.
6. Generates the first `frontend/public/build-info.json`.

Verify:

```powershell
python scripts/version.py check
```

Show versions:

```powershell
python scripts/version.py show
```

---

## Normal Development

Do not bump the application version for every commit.

Multiple feature, fix, test, documentation, and infrastructure commits may
belong to the same LibraryForge version.

For example:

```text
0.1.0-alpha.3

feat: add local artwork management
feat: add user settings and application controls
docs: finalize 0.1.0-alpha.3 changelog
```

can all belong to the same product version.

When starting Vite:

```powershell
npm run dev
```

npm automatically runs:

```text
predev
→ python ../scripts/version.py prepare-frontend
```

Likewise:

```powershell
npm run build
```

automatically runs:

```text
prebuild
→ python ../scripts/version.py prepare-frontend
```

This captures the exact Git commit and dirty state for the frontend build.

The backend obtains its runtime Git identity independently from the repository
or configured build environment.

---

## Development Milestone Workflow

LibraryForge currently bumps the working product version when development of
the next milestone begins.

Example:

```text
Finish 0.1.0-alpha.3 feature work
        ↓
Test the completed alpha.3 milestone
        ↓
Finalize CHANGELOG.md for 0.1.0-alpha.3
        ↓
Commit the alpha.3 release boundary
        ↓
Set VERSION to 0.1.0-alpha.4
        ↓
Begin alpha.4 development
```

To start the next milestone:

```powershell
python scripts/version.py set 0.1.0-alpha.4
python scripts/version.py check
```

This changes all synchronized product-version sources together.

The version bump may be committed with the first meaningful commit of the new
milestone or as its own maintenance commit.

Do not change the version merely because another commit was created.

---

## Current Planned Version Progression

The current roadmap is:

```text
0.1.0-alpha.1
Semantic catalog and Needs Attention foundation
Completed

0.1.0-alpha.2
Canonical metadata editor
Completed

0.1.0-alpha.3
Local artwork management and application housekeeping
Current / completing

0.1.0-alpha.4
Online Video / TubeArchivist catalog

0.1.0-alpha.5
Metadata providers

0.1.0-alpha.6
Projection and output engine

0.1.0-alpha.7
Safe library operations

0.1.0-alpha.8
Reliability and deployment

0.1.0-beta.1
Full-system beta testing

0.1.0-beta.N
Additional beta cycles only when required

0.1.0-rc.1
First 1.0 release candidate

0.1.0-rc.N
Additional release candidates only when required

1.0.0
First stable LibraryForge release
```

The detailed feature roadmap is maintained in:

```text
ROADMAP.md
```

These milestone numbers describe the current plan. They may change if the scope
of a future milestone changes substantially.

---

## Alpha Versions

Alpha versions are active development builds.

Examples:

```text
0.1.0-alpha.3
0.1.0-alpha.4
```

During alpha development, LibraryForge may still make substantial changes to:

* database models
* APIs
* metadata structures
* workflows
* deployment architecture
* configuration
* user interface behavior

Backward compatibility between every alpha build is not guaranteed.

Migration paths should still be preserved whenever practical.

---

## Beta Versions

Beta begins when the major planned LibraryForge subsystems are implemented and
the development focus moves primarily toward real-world validation.

Example:

```text
0.1.0-beta.1
```

Beta work should focus primarily on:

* bugs
* edge cases
* performance
* large-library behavior
* installation
* upgrades
* security
* permissions
* deployment
* backup and recovery
* usability
* integration testing

Additional beta versions are created only when another testing cycle is
necessary:

```text
0.1.0-beta.2
0.1.0-beta.3
```

Do not pre-plan an arbitrary number of beta releases.

---

## Release Candidates

A release candidate means the LibraryForge feature set intended for `1.0.0` is
effectively frozen.

Example:

```text
0.1.0-rc.1
```

Release-candidate work should be restricted primarily to release blockers such
as:

* correctness bugs
* data-integrity problems
* security vulnerabilities
* installation failures
* migration failures
* serious compatibility problems
* documentation required for release

Normal new feature development should stop during the release-candidate phase.

If fixes are required:

```text
0.1.0-rc.2
0.1.0-rc.3
```

are created as needed.

When a release candidate satisfies the stable-release criteria documented in
`docs/RELEASE_STRATEGY.md`, LibraryForge is promoted directly to:

```text
1.0.0
```

There is no requirement to publish a plain `0.1.0` release first.

---

## Stable Versions

`1.0.0` is the first stable LibraryForge release.

After `1.0.0`, normal Semantic Versioning applies.

Examples:

```text
1.0.1
```

Backward-compatible bug fix.

```text
1.1.0
```

Backward-compatible new functionality.

```text
2.0.0
```

Intentional breaking change to a stable public contract.

The exact public contracts covered by compatibility guarantees will be
documented before `1.0.0`.

---

## Git Tags

Git tags identify exact preserved versions.

The tag must exactly match:

```text
v + VERSION
```

Example:

```powershell
git tag -a v0.1.0-beta.1 -m "LibraryForge 0.1.0-beta.1"
git push origin v0.1.0-beta.1
```

or:

```powershell
git tag -a v1.0.0 -m "LibraryForge 1.0.0"
git push origin v1.0.0
```

Tags may also be created for important alpha snapshots when preserving an exact
build is useful.

LibraryForge does not need a GitHub Release for every development commit or
every local alpha build.

Formal GitHub Releases become more important during beta, release-candidate,
and stable distribution.

---

## GitHub Actions

`.github/workflows/version-consistency.yml` runs on pushes to `main`, pull
requests, and version tags.

It verifies:

```text
VERSION
backend/pyproject.toml
frontend/package.json
```

all agree.

For a tag such as:

```text
v0.1.0-rc.1
```

it additionally verifies that the tag matches:

```text
v + VERSION
```

The general CI workflow separately validates backend tests and the frontend
production build.

---

## Production / Containers

The backend can read build identity from Git when `.git` exists.

For production images where `.git` is intentionally absent, these environment
variables are supported:

```text
LIBRARYFORGE_VERSION
LIBRARYFORGE_GIT_SHA
LIBRARYFORGE_GIT_BRANCH
LIBRARYFORGE_GIT_DIRTY
LIBRARYFORGE_BUILD_TIME
```

A future production Docker build should inject those values through CI/build
arguments.

`LIBRARYFORGE_VERSION` is an override.

Normally the root `VERSION` file remains the canonical product-version source.

---

## Database Versions

Do not create a second LibraryForge database-version number.

Django migrations are the database schema history.

Application versions and database migration numbers solve different problems:

```text
LibraryForge version
→ product/release identity

Django migrations
→ database schema history
```

Both are required, but they should not be synchronized numerically.

---

## API Versions

Do not add `/api/v1/` solely because LibraryForge has reached a particular
application version.

LibraryForge currently ships its React frontend and Django backend together.

Explicit API versioning should be introduced when LibraryForge has a real need
to support external clients, plugins, integrations, or multiple
backward-compatible API contracts simultaneously.

Reaching `1.0.0` does not by itself require changing all API routes to
`/api/v1/`.

---

## Related Documentation

```text
VERSION
    Canonical current product version

ROADMAP.md
    Product milestones and planned capabilities

CHANGELOG.md
    User-visible changes by released/development version

docs/VERSIONING.md
    Technical product-version implementation and workflow

docs/RELEASE_STRATEGY.md
    Alpha, beta, release-candidate, and stable promotion policy
```
