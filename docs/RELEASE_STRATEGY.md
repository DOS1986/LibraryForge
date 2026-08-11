# LibraryForge Release Strategy

LibraryForge follows Semantic Versioning and uses explicit pre-release identifiers before the first stable release.

## Version path to 1.0

```text
0.1.0-alpha.1
0.1.0-alpha.2
...
0.1.0-alpha.N
        ↓
0.1.0-beta.1
0.1.0-beta.N
        ↓
0.1.0-rc.1
0.1.0-rc.N
        ↓
1.0.0
```

LibraryForge does not plan to call plain `0.1.0` a stable release. Versions with major version `0` remain initial-development versions.

## Alpha

Alpha builds are development milestones. Major capabilities, architecture, models, APIs, and workflows may still change.

Alpha work can include:

- new major subsystems
- schema/model redesign
- API changes
- workflow changes
- large refactors
- experimental product decisions

An alpha build is considered complete when its planned milestone is tested, committed, documented in `CHANGELOG.md`, and the next development version begins.

## Beta

Beta begins when the intended 1.0 core feature set is substantially complete.

Beta work should focus on validating the entire product:

- real-world libraries
- installation and onboarding
- upgrades and migrations
- reliability
- performance
- permissions and security
- backup/restore
- supported deployment methods
- UX and accessibility
- documentation

Beta may still include meaningful changes when testing demonstrates they are necessary, but the project should avoid adding unrelated major subsystems.

There is no predetermined number of beta releases. Produce `beta.2`, `beta.3`, and so on only when another validation cycle is needed.

## Release Candidate

An RC is a build LibraryForge believes could become `1.0.0`.

RC rules:

- feature freeze
- fix release blockers only
- avoid speculative refactors
- verify fresh installs
- verify upgrades/migrations
- verify backup and recovery
- verify supported production deployment methods
- complete security review
- complete release documentation

If a blocker is found, fix it and publish another RC.

## Promoting an RC to 1.0.0

Promote the latest RC to `1.0.0` only when:

- no known release-blocking security defects remain
- no known release-blocking data-loss defects remain
- supported fresh installs work
- supported upgrades work
- database migrations are validated
- background-job recovery behavior is validated
- backup/restore is documented and tested
- supported deployment paths are documented and tested
- the 1.0 product behavior and safety guarantees are documented
- release documentation is complete

Ideally the promotion from the final RC to `1.0.0` changes release metadata/versioning rather than introducing new functional code.

## After 1.0.0

Once LibraryForge reaches 1.0, normal Semantic Versioning becomes the stable contract:

- Patch: `1.0.1` — backwards-compatible fixes
- Minor: `1.1.0` — backwards-compatible functionality
- Major: `2.0.0` — incompatible changes to the stable public/product contract

## Changelog behavior

During active development, changes accumulate under `## [Unreleased]`.

When a milestone is finalized:

1. Convert the accumulated release content into the completed version section.
2. Restore a new empty `## [Unreleased]` section above it.
3. Commit the release-boundary documentation.
4. Bump to the next development version before beginning the next milestone's code.

Pre-release identifiers are part of the version and should be recorded exactly in the changelog.
