# Security Policy

## Supported versions

LibraryForge is currently in active pre-1.0 development.

| Version | Supported |
| --- | --- |
| Current development version | Yes |
| Older alpha/beta/RC development versions | Best effort |
| Unreleased local modifications | No guarantee |

Until LibraryForge reaches 1.0, security fixes may require updating to the latest supported pre-release rather than receiving a backport. Release candidates receive priority for release-blocking security fixes.

## Reporting a vulnerability

Please do **not** disclose security vulnerabilities in a public GitHub issue.

If GitHub private vulnerability reporting is enabled for this repository, use the repository's **Report a vulnerability** action under the Security section.

If private vulnerability reporting is not available, open a public issue that contains **no vulnerability details** and asks the maintainer for a private reporting channel.

A useful private report should include:

- affected LibraryForge version or commit
- affected operating system/deployment type
- reproduction steps
- expected and actual behavior
- potential impact
- proof-of-concept information when safe to share
- any suggested mitigation

## Security-sensitive areas

Please treat findings involving these areas as security reports:

- authentication or session handling
- CSRF or authorization bypass
- path traversal or access outside configured library roots
- arbitrary command or process execution
- application restart/supervisor controls
- filesystem write restrictions and library management modes
- credential or secret exposure
- metadata-provider credentials
- unsafe archive/file parsing
- SQL injection
- cross-site scripting
- privilege escalation
- unauthorized access to media, NFO, artwork, or metadata
- unsafe symlink/hardlink/projection behavior

## Disclosure

Please allow reasonable time to investigate and prepare a fix before public disclosure. When appropriate, fixes and disclosure information will be handled through a GitHub Security Advisory.
