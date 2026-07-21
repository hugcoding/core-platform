# Operations Runbook

Deze pagina is de snelle cockpit voor dagelijkse CORE- en beheercommands.

## Waar draai ik commands?

Gebruik de NAS voor runtime, cleanup en databasechecks:

```bash
cd /volume1/docker/nas-stack
core doctor
core runtime status
core cleanup assess
```

Gebruik Windows PowerShell voor commands die lokaal op Windows zijn ingericht:

```powershell
cd "\\NAS\docker\nas-stack"
.\tools\windows\core.ps1 docs build
```

`core docs build` werkt op de NAS alleen als MkDocs daar ook is geinstalleerd.

## Veelgebruikte CORE commands

```bash
core doctor
core docs build
core docs serve
core docs open
core runtime status
core runtime health
core runtime dlq
core runtime cleanlocks
core cleanup assess
core cleanup legacy-duplicates --dry-run
core cleanup legacy-duplicates --apply --confirm-delete-legacy-duplicates
core jira auth
core jira stories --project SCRUM --limit 50
```

## Docker Compose deployment

Voer deze commands op de NAS uit vanuit de repository:

```bash
cd /volume1/docker/nas-stack
```

Verwijder de scanner- en workercontainers, bouw beide images volledig opnieuw en maak de containers opnieuw aan:

```bash
/usr/local/bin/docker compose rm -sf scanner metadata_worker
/usr/local/bin/docker compose build --no-cache scanner metadata_worker
/usr/local/bin/docker compose up -d --force-recreate scanner metadata_worker
```

Controleer daarna status en logs:

```bash
/usr/local/bin/docker compose ps
/usr/local/bin/docker compose logs --tail=100 scanner metadata_worker
./tools/runtime/status
```

Voor een normale rebuild zonder eerst containers te verwijderen:

```bash
/usr/local/bin/docker compose up -d --build scanner metadata_worker
```

Voor de volledige stack:

```bash
/usr/local/bin/docker compose up -d --build
```

Stoppen en opnieuw starten zonder rebuild:

```bash
/usr/local/bin/docker compose down
/usr/local/bin/docker compose up -d
```

## Documentation workflow

Build de documentatie via CORE:

```bash
core docs build
```

Als Windows de enige omgeving met MkDocs is:

```powershell
.\tools\windows\core.ps1 docs build
```

Start de lokale docs server:

```bash
core docs serve
```

Open de portal:

```bash
core docs open
```

De Material for MkDocs 2.0 waarschuwing is upstream en geen build failure zolang MkDocs eindigt met `Documentation built`.

## Cleanup workflow

Maak eerst een databasebackup. Zie [PostgreSQL](postgres.md#backup-before-cleanup).

Run daarna de read-only assessment:

```bash
core cleanup assess
```

Run de legacy duplicate dry-run:

```bash
core cleanup legacy-duplicates --dry-run
```

Controleer de exports:

```bash
ls -lh project/exports/controlled-cleanup/
cat project/exports/controlled-cleanup/latest.md
```

Controleer vooral:

- `latest-summary.csv`
- `latest-candidates.csv`
- `latest-blocked.csv`
- `latest-cascade-impact.csv`
- `latest-size-mismatches.csv`

Apply mag pas na backup en controle:

```bash
core cleanup legacy-duplicates --apply --confirm-delete-legacy-duplicates
```

Verifieer daarna opnieuw:

```bash
core cleanup legacy-duplicates --dry-run
core cleanup assess
```

## Database backup

Vanaf de NAS:

```bash
cd /volume1/docker/nas-stack
mkdir -p project/exports/db-backups
docker exec postgres pg_dump -U hugo -d nasdb_test -Fc > project/exports/db-backups/nasdb_test-before-cleanup-$(date +%Y%m%d-%H%M%S).dump
ls -lh project/exports/db-backups | tail -5
```

Vanuit Windows PowerShell via SSH:

```powershell
ssh hugo@NAS "cd /volume1/docker/nas-stack && mkdir -p project/exports/db-backups && /usr/local/bin/docker exec postgres pg_dump -U hugo -d nasdb_test -Fc > project/exports/db-backups/nasdb_test-before-cleanup-$(date +%Y%m%d-%H%M%S).dump && ls -lh project/exports/db-backups | tail -5"
```

## Niet in Git

Deze lokale bestanden en mappen horen niet in Git:

```text
core/cache/
core/secrets/credentials.yaml
project/exports/db-backups/
project/exports/controlled-cleanup/
project/exports/legacy-assessment/
site/
```
