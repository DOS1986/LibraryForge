# LibraryForge Privacy Principles

LibraryForge is designed as a self-hosted application. The default architecture keeps library metadata, user accounts, preferences, scan history, and media management data on the LibraryForge server controlled by the operator.

This document describes project privacy principles during pre-1.0 development. It is not a legal privacy policy for a hosted commercial service.

## Default behavior

LibraryForge should not require a hosted LibraryForge account or cloud service to manage local libraries.

The application should not send local library contents, filenames, metadata, user information, or usage analytics to LibraryForge-operated infrastructure by default.

## Telemetry

LibraryForge currently has no required product telemetry service.

If optional diagnostics or telemetry are introduced later, they should be:

- clearly documented
- disabled by default unless there is a strong operational reason otherwise
- configurable by the server operator
- limited to the minimum information needed
- separated from media/library content wherever possible

## External metadata providers

Future metadata-provider integrations may send search terms, media titles, external IDs, or similar lookup information to the provider selected by the operator.

Provider integrations must be optional and should clearly identify:

- which external service is contacted
- what information is sent
- which credentials are stored
- how the integration can be disabled

Provider responses should be treated as enrichment data and recorded with provenance.

## TubeArchivist and online-video libraries

LibraryForge should prefer metadata already present in the local archive before requiring a live connection to TubeArchivist, YouTube, or another external service.

## Credentials

Secrets and provider credentials must not be written to logs or committed to the source repository.

Production credential-storage requirements will be finalized during beta and must be complete before the first release candidate.

## Media files

LibraryForge does not need to upload media files to a LibraryForge-operated service in order to perform its normal self-hosted metadata-management functions.

## Changes to these principles

Privacy-affecting architecture changes should be documented in the changelog and this file before the first release candidate. The privacy behavior intended for the stable product should be considered frozen during RC except for fixes.
