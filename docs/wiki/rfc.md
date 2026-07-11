# RFC's

Aantal RFC's: `1`

## RFC-0001-core-foundation

- Titel: `RFC-0001 - CORE Foundation`
- Status: `Accepted`
- Bestand: `docs\rfc\RFC-0001-core-foundation.md`
- Regels: `27`

```markdown
# RFC-0001 - CORE Foundation

## Status

Accepted

## Goal

Introduce a stable project structure for CORE without breaking the existing scanner and metadata pipeline.

## Scope

- Add core manifest.
- Add database folder structure.
- Add RFC and standards folders.
- Keep existing runtime files in place.

## Non-goals

- Do not move scanner.py yet.
- Do not move metadata_worker.py yet.
- Do not change Docker Compose behavior yet.
- Do not clean legacy database records yet.

## Outcome

CORE 2.1 becomes the foundation for future Dispatcher, Job Engine, Integrity Engine and Documentation Engine work.
```

