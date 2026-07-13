# Changelog

## CORE 2.2 - Governance & DX

### Added

- SCRUM-19 legacy assessment command: `core cleanup assess` with read-only database reports.
- SCRUM-20 controlled cleanup dry-run command: `core cleanup legacy-duplicates --dry-run` with candidate, blocked and cascade-impact reports.
- SCRUM-20 controlled cleanup apply mode with explicit confirmation guard for legacy duplicate database rows.
- PostgreSQL backup, restore and command pitfall documentation for cleanup preparation.
- Jira integration read-only foundation with auth, epics/stories dry-run, issue mapping and local cache.
- Configuration-driven CORE CLI.
- CORE docs commands: `core docs serve`, `core docs build`, `core docs open`.
- Windows and NAS CORE wrappers for docs commands.

### Changed

- MkDocs navigation now includes generated documentation, ADR, RFC and standards sources.
- `DOCUMENTATIE.md` links now target the MkDocs wiki pages.

### Validated

- `core doctor` OK.
- `python -m unittest discover -s tests` OK.
- `core docs build` OK on Windows through CORE CLI.

## CORE 2.1 - Foundation

### Added

- SCRUM-19 legacy assessment command: `core cleanup assess` with read-only database reports.
- Scanner
- Metadata Worker
- Health Engine
- Integrity Engine
- Documentation Engine
- Standards Engine
- Project Intelligence Engine foundation
