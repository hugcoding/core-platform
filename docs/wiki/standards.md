# CORE Standards

Aantal standaarden: `7`

## Database Standard

- Bestand: `docs/standards/database.md`
- Regels: `10`

```markdown
# Database Standard

Rules:

- No DELETE without migration plan.
- Use views for analysis.
- Integrity Engine is leading.
- Schema changes must be documented.
- New tables require documentation.
- Cleanup must start with dry-run.
```

## Docker Standard

- Bestand: `docs/standards/docker.md`
- Regels: `9`

```markdown
# Docker Standard

Rules:

- Runtime components run in Docker.
- Containers must restart unless stopped.
- Healthchecks are preferred.
- Environment variables must be documented.
- Volumes must be explicit.
```

## Documentation Standard

- Bestand: `docs/standards/documentation.md`
- Regels: `10`

```markdown
# Documentation Standard

Rules:

- New modules must be documented.
- New Redis streams must be documented.
- New database views must be documented.
- ADRs explain why.
- RFCs explain what is proposed.
- Documentation must be regenerated before release.
```

## Project Standard

- Bestand: `docs/standards/project.md`
- Regels: `14`

```markdown
# Project Standard

## Mission

Build a robust, observable and self-documenting NAS Metadata Platform.

## Principles

- Platform before features.
- Integrity first.
- Documentation is code.
- Architecture before implementation.
- No cleanup without dry-run.
- Runtime and development stay separated.
```

## Redis Standard

- Bestand: `docs/standards/redis.md`
- Regels: `10`

```markdown
# Redis Standard

Rules:

- Use clear key names.
- Heartbeats require TTL.
- Locks require TTL.
- Streams require DLQ strategy.
- No random Redis keys.
- New streams must be documented.
```

## Release Standard

- Bestand: `docs/standards/releases.md`
- Regels: `12`

```markdown
# Release Standard

## Release checklist

- [ ] Build succeeds
- [ ] Containers start
- [ ] Health OK
- [ ] Heartbeats active
- [ ] Documentation generated
- [ ] Integrity checked
- [ ] Changelog updated
- [ ] ADR/RFC updated if needed
```

## Worker Standard

- Bestand: `docs/standards/workers.md`
- Regels: `12`

```markdown
# Worker Standard

Every worker must have:

- Heartbeat
- Healthcheck
- Redis lock
- Logging
- Graceful shutdown
- Retry or DLQ strategy
- Documentation
- ADR when architecture changes
```

