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

De realtime watcher installeert zijn eigen lichte dependency bovenop het bestaande basisimage. Bouw en start alleen de watcher voor de eerste uitrol:

```bash
/usr/local/bin/docker compose build watcher
/usr/local/bin/docker compose up -d watcher
```

Controleer daarna status en logs:

```bash
/usr/local/bin/docker compose ps
/usr/local/bin/docker compose logs --tail=100 watcher
./tools/runtime/status
```

Scanner, metadata-worker, Redis en PostgreSQL hoeven voor deze eerste watcheruitrol niet opnieuw te worden gebouwd of gestart.

De eerste veilige uitrol bewaakt standaard alleen de canonieke doelroot:

```text
WATCH_ROOTS=/volume1/data
```

Dit voorkomt een langdurige eerste registratie van alle legacy- en applicatiemappen onder `/volume1`. Meerdere expliciet goedgekeurde hoofdroots kunnen later kommagescheiden worden toegevoegd. De uur- en dagscanner blijven alle geconfigureerde scanroots controleren.

Voor een normale rebuild zonder eerst containers te verwijderen:

```bash
/usr/local/bin/docker compose up -d --build scanner watcher metadata_worker
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

### Full- en intervalscans controleren

```bash
/usr/local/bin/docker compose logs --tail=100 scanner
./tools/runtime/status
```

Runtime-status toont afzonderlijk de laatste full scan, intervalscan en intervalroot. Controleer in `scan_sessions` dat beide types voorkomen:

```bash
/usr/local/bin/docker exec postgres psql -U hugo -d nasdb_test -c \
"SELECT type,status,started_at,finished_at,files_discovered,jobs_enqueued,jobs_processed
 FROM scan_sessions
 ORDER BY started_at DESC
 LIMIT 10;"
```

### Realtime watcher controleren

```bash
core runtime health
core runtime status
/usr/local/bin/docker compose logs --tail=100 watcher
```

De status toont:

- watcher heartbeat en status;
- tijdstip van het laatste bestandsevent;
- aantal roots dat na watcherstart voor herstel is ingepland;
- huidige dirty roots die nog op gerichte reconciliation wachten.

Realtime watcher-events gebruiken `scan_stream_realtime`. De metadata-worker controleert deze prioriteitsstream vóór iedere kleine batch uit de pollingstream `scan_stream`. Daardoor blijven create, modify, move, rename en delete realtime verwerkbaar wanneer een full scan duizenden achtergrondjobs heeft ingepland.

Bij iedere watcherstart worden de toegestane hoofdroots als dirty gemarkeerd. De scanner behandelt deze roots één voor één vóór de gewone intervalrotatie. Een marker wordt alleen verwijderd wanneer de controle slaagt en er tijdens die controle geen nieuwer event voor dezelfde root is geregistreerd.

Maak voor de eerste acceptatietest uitsluitend een tijdelijke map onder `/volume1/data` en test daar create, modify, rename, move en delete. Gebruik geen productie- of legacybestanden voor deze test.

De live acceptatietest van 2026-07-26 verwerkte create en modify binnen 2 seconden, rename en move binnen 4 seconden en delete binnen 2 seconden. Zie [SCRUM-55 Realtime Scanning](../project/scrum-55-realtime-scanning.md).

### Container Manager-namen

Sluit Synology Container Manager voordat services met `docker compose up -d --force-recreate` opnieuw worden aangemaakt. Wanneer de GUI tijdens een recreatie geopend blijft, kan Container Manager een oude container-ID als prefix tonen terwijl Docker zelf nog de juiste naam gebruikt.

Controleer altijd de werkelijke namen met:

```bash
docker ps --format '{{.Names}}'
```

## NAS repository veilig bijwerken

Gebruik vanuit Windows PowerShell het wrapper-script. Het controleert op lokale NAS-wijzigingen, schakelt automatisch Git-onderhoud op de SMB-share uit en staat alleen een fast-forward toe:

```powershell
cd C:\Development\nas-stack
.\tools\windows\nas-pull.ps1
```

Via de CORE-wrapper kan hetzelfde met:

```powershell
.\tools\windows\core.ps1 git pull
```

Gebruik geen gewone `git pull` vanuit `\\NAS\docker\nas-stack`; packfile-renames en automatisch repository-onderhoud zijn via SMB niet betrouwbaar. De wrapper zet `maintenance.auto=false` voor zowel fetch als merge, omdat beide commands anders na hun hoofdactie alsnog een repack kunnen starten.

## Documentation workflow

Ontwikkel documentatie lokaal in `C:\development\nas-stack\docs`. De
permanente NAS-Wiki start je vanuit SSH zonder foreground-proces:

```bash
cd /volume1/docker/nas-stack
core docs serve
```

Het commando start `nas-docs-1` op de achtergrond. Open daarna:

```text
http://192.168.68.105:8000/wiki/
```

Alleen voor een tijdelijke MkDocs-ontwikkelserver op NAS-loopback:

```bash
core docs dev
```

`core docs dev` blokkeert de terminal en is vanaf een laptop alleen via een
SSH-tunnel bereikbaar. Gebruik dit niet voor de permanente Wiki.

Na review en merge naar `main` voer je vanuit SSH op de NAS uit:

```bash
cd /volume1/docker/nas-stack
core git pull
```

CORE gebruikt hiervoor een tijdelijke Git-container; Git hoeft niet als
Synology-pakket geïnstalleerd te zijn. Als `docs/`, `mkdocs.yml`, de docs-
Dockerfile of nginx-configuratie is gewijzigd, rebuildt `core git pull`
automatisch `nas-docs-1`. Bij andere wijzigingen blijft de docs-container
ongemoeid.

Controleer na een automatische publicatie de containerstatus met
`docker compose ps docs` en open `/wiki/` in de browser.

De Material for MkDocs 2.0-waarschuwing is upstream en geen build failure
zolang MkDocs eindigt met `Documentation built`.

## Cleanup workflow

### Database schema review

Run the read-only SCRUM-53 assessment before proposing column removal:

```bash
cd /volume1/docker/nas-stack
/usr/local/bin/docker exec -i postgres psql -U hugo -d nasdb_test \
  < database/assessment/schema_review.sql
```

The assessment contains only `SELECT` statements. The current evidence and candidate classifications are documented in `project/reports/SCRUM-53-database-schema-review.md`.

Maak eerst een databasebackup. Zie [PostgreSQL](postgres.md).

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

## Permanente CORE-documentatie

De documentatie wordt tijdens de image-build statisch gegenereerd en door een
read-only nginx-container aangeboden. Er draait geen MkDocs-ontwikkelserver in
productie.

Build en start alleen de documentatieservice:

```bash
cd /volume1/docker/nas-stack
docker compose build docs
docker compose up -d docs
docker compose ps docs
```

Open thuis of via OpenVPN:

```text
http://192.168.68.105:8000/wiki/
```

De root-URL `http://192.168.68.105:8000/` verwijst automatisch door naar
`/wiki/`. De hostpoort bindt alleen aan het LAN-adres van de NAS. Er hoort geen
port-forward voor poort 8000 op het KPN-modem te bestaan. De DSM-firewall staat
alleen het lokale netwerk `192.168.68.0/24` en het VPN-netwerk `10.8.0.0/24`
toe.

Na review, merge en `core git pull` publiceer je de goedgekeurde versie:

```bash
cd /volume1/docker/nas-stack
core docs deploy
```

Hierdoor worden lokale conceptwijzigingen nooit automatisch gepubliceerd.
Alleen de gereviewde Git-versie uit de NAS-checkout wordt in `nas-docs-1`
opgenomen.
