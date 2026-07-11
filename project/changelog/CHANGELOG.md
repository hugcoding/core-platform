# Changelog

## CORE 2.2 - Governance & DX

### Added

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

- Scanner
- Metadata Worker
- Health Engine
- Integrity Engine
- Documentation Engine
- Standards Engine
- Project Intelligence Engine foundation
