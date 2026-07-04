# NAS Metadata Platform - Sprint 1.6 Release

## Doel

Sprint 1.6 voegt expliciete heartbeats en betere health/status-controles toe.

## Bestanden

- scanner.py
- metadata_worker.py
- health
- status

## Nieuwe Redis keys

Scanner:

- scanner:heartbeat
- scanner:heartbeat:status
- scanner:last_scan

Metadata worker:

- metadata_worker:heartbeat
- metadata_worker:heartbeat:status
- metadata_worker:last_event

## Installatie

Maak eerst een backup:

```bash
cd /volume1/docker/nas-stack
mkdir -p backup/sprint1_6
cp scanner.py metadata_worker.py status health backup/sprint1_6/ 2>/dev/null || true
```

Vervang daarna de bestanden uit deze release.

Deploy:

```bash
docker compose build --no-cache scanner metadata_worker
docker compose up -d --force-recreate scanner metadata_worker
./status
./health
```
