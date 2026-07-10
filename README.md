# CORE Platform

A modular platform for runtime orchestration, project intelligence, governance and documentation automation.

## Engines

- Documentation Engine
- Project Intelligence Engine
- Governance Engine
- Runtime Engine
- Metadata Engine

## CORE CLI

Use the CORE CLI as the entry point for documentation commands. MkDocs is configured through `paths.mkdocs` in `core/config/core.yaml` and should be accessed through CORE:

```bash
core docs serve
core docs build
core docs open
```

`core docs open` opens `http://127.0.0.1:8000` in the default browser.

`core docs build` has been validated through the CORE CLI on Windows. The remaining Material for MkDocs warning is upstream and not a project build failure.

## Technology

- Python
- Docker
- PostgreSQL
- Redis
- MkDocs
- Jira
- GitHub

## Current Release

CORE Platform v2.2 - Foundation
