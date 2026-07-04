# CORE Manifest

## Platform

- `name`: `NAS Metadata Platform`
- `version`: `2.2.0`
- `release`: `CORE Governance`

## Modules

### `scanner`

- `enabled`: `True`

### `metadata_worker`

- `enabled`: `True`

## Engines

### `documentation`

- `enabled`: `True`

### `project_intelligence`

- `enabled`: `True`

### `integrity`

- `enabled`: `True`

### `health`

- `enabled`: `True`

## Bron: core/core.yaml

```yaml
platform:
  name: NAS Metadata Platform
  version: 2.2.0
  release: CORE Governance

paths:
  root: /volume1/docker/nas-stack
  scan_root: /volume1

modules:
  scanner:
    enabled: true
  metadata_worker:
    enabled: true

engines:
  documentation:
    enabled: true
  project_intelligence:
    enabled: true
  integrity:
    enabled: true
  health:
    enabled: true
```
