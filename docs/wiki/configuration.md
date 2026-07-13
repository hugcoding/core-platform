# Configuration

CORE gebruikt twee soorten instellingen:

- Configuratie staat in `core/config/` en mag in Git staan.
- Secrets staan in `core/secrets/` en blijven lokaal op de NAS/workstation-combinatie.

## Configuratiebestanden

`core/config/core.yaml` bevat applicatiegegevens en paden die de CORE CLI nodig heeft, zoals de Windows repository-locatie, de NAS-root, SSH-doelgegevens en de MkDocs-configuratie.

`core/config/logging.yaml` bevat loggingniveau en loggingformat.

`core/config/projects.yaml` bevat projectmetadata zoals project key, naam en repositorynaam.

Deze bestanden beschrijven hoe CORE draait en waar onderdelen staan. Ze bevatten geen tokens of wachtwoorden.

## Documentatiepad

De CORE CLI leest de MkDocs-configuratie uit `paths.mkdocs` in `core/config/core.yaml`:

```yaml
paths:
  docs: docs
  mkdocs: mkdocs.yml
```

Gebruik MkDocs via CORE:

```powershell
core docs serve
core docs build
core docs open
```

`core docs serve` start MkDocs op `127.0.0.1:8000`, `core docs build` bouwt de site, en `core docs open` opent `http://127.0.0.1:8000` in de standaardbrowser.

Als `mkdocs.yml` ontbreekt, geeft CORE een duidelijke foutmelding met het geconfigureerde pad.

## Secrets

`core/secrets/credentials.example.yaml` is het template voor lokale credentials. Dit bestand staat wel in Git, zodat duidelijk is welke velden nodig zijn.

Maak je lokale secrets-bestand zo:

```powershell
Copy-Item core\secrets\credentials.example.yaml core\secrets\credentials.yaml
```

Vul daarna in `core/secrets/credentials.yaml` je eigen waarden in voor GitHub en Jira:

```yaml
github:
  token: "..."
  owner: "..."

jira:
  url: "https://your-domain.atlassian.net"
  email: "you@example.com"
  token: "..."
```

## Waarom credentials.yaml genegeerd wordt

`core/secrets/credentials.yaml` bevat persoonlijke tokens. Het bestand staat daarom in `.gitignore` en mag niet worden gecommit. Alleen `credentials.example.yaml` hoort in Git.

## Configuratie controleren

Gebruik de CORE doctor om config en secrets te valideren:

```powershell
core doctor
```

De doctor controleert of alle verplichte bestanden bestaan en of verplichte velden zoals `paths.mkdocs`, `github.token`, `github.owner`, `jira.url`, `jira.email` en `jira.token` gevuld zijn.
## Jira integration

PROJECT-005 starts with a read-only Jira integration slice. CORE uses `jira.url`, `jira.email` and `jira.token` from `core/secrets/credentials.yaml`.

Issue search uses Jira Cloud enhanced search: /rest/api/3/search/jql.

Use dry-run first to inspect the JQL without calling Jira:

```powershell
core jira epics --project SCRUM --dry-run
core jira stories --project SCRUM --dry-run
core jira sync --project SCRUM --dry-run
```

Use the auth check to verify credentials:

```powershell
core jira auth
```

Read-only fetch commands write local cache files under `core/cache/jira/`, which is ignored by Git:

```powershell
core jira epics --project SCRUM --limit 50
core jira stories --project SCRUM --limit 50
```
## Cleanup assessment

SCRUM-19 Legacy Assessment is read-only. It inspects PostgreSQL and writes reports under `project/exports/legacy-assessment/`.

```powershell
core cleanup assess
```

The assessment exports summary, extension, noise, duplicate hash, reconstructed path and missing metadata CSV files. It does not delete or update database rows. SCRUM-20 Controlled Cleanup should use these reports as input and still run dry-run first.

## Controlled cleanup dry-run

SCRUM-20 starts with a legacy duplicate dry-run. It matches legacy rows without `path`, `hash_content` and `hash_path` to active canonical rows with the same reconstructed path.

```powershell
core cleanup legacy-duplicates --dry-run
```

The dry-run writes reports under `project/exports/controlled-cleanup/`, including candidate rows, blocked legacy rows, size mismatches and cascade impact for metadata, embeddings and AI output. It does not delete or update database rows.

After a verified database backup, apply mode can delete only the matched legacy duplicate database rows. Files on disk are not removed. Apply mode requires an explicit confirmation flag:

```powershell
core cleanup legacy-duplicates --apply --confirm-delete-legacy-duplicates
```

After apply mode, run `core cleanup legacy-duplicates --dry-run` and `core cleanup assess` again to verify the cleanup result.
