# LibraryForge Versioning

LibraryForge uses one product version across the entire application.

The authoritative version is stored at the repository root:

```text
VERSION
```

Example:

```text
0.1.0-alpha.1
```

Do not independently invent frontend and backend product versions.

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
  "version": "0.1.0-alpha.1",
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

## Normal Development

You do not bump the application version for every commit.

Normal feature/fix commits can remain on the current application version.

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

## Changing the Product Version

From the repository root:

```powershell
python scripts/version.py set 0.1.0-alpha.2
```

That changes all product-version sources together.

Then verify:

```powershell
python scripts/version.py check
```

Commit the version bump with the milestone it represents.

Example:

```text
feat: add canonical metadata editor
```

## Recommended Early Version Progression

```text
0.1.0-alpha.1   semantic catalog / Needs Attention baseline
0.1.0-alpha.2   canonical metadata editor
0.1.0-alpha.3   artwork management
0.1.0-alpha.4   metadata provider integration
0.2.0-alpha.1   mature output/projection workflow
0.5.0-beta.1    broader testing
1.0.0           first stable release
```

These are guidelines, not a requirement to bump after every named feature.

## Git Tags

When LibraryForge reaches an installable alpha worth preserving:

```powershell
git tag -a v0.1.0-alpha.1 -m "LibraryForge 0.1.0-alpha.1"
git push origin v0.1.0-alpha.1
```

The tag must exactly match:

```text
v + VERSION
```

The GitHub workflow verifies this automatically.

You do not need to create GitHub Releases yet.

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
v0.1.0-alpha.1
```

it additionally verifies that the tag matches `VERSION`.

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

A future application Docker build should inject those values from CI/build
arguments.

`LIBRARYFORGE_VERSION` is an override. Normally the root `VERSION` file remains
the canonical source.

## Database Versions

Do not create a second LibraryForge database-version number.

Django migrations are the database schema version history.

## API Versions

Do not add `/api/v1/` yet.

LibraryForge currently ships the React frontend and Django backend together.
API generation/versioning should be introduced only when external clients,
plugins, or backward-compatible API contracts require it.
