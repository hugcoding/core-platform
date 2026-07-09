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
