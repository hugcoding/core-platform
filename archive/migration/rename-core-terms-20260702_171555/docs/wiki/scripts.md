# Scripts

## `rebuild`

Bouwt scanner en metadata_worker opnieuw.

- Bestaat: `True`
- Regels: `13`
- Gebruikt docker compose: `True`
- Gebruikt Redis: `False`

```bash
#!/bin/bash
set -e
cd /volume1/docker/nas-stack
echo "========== DOCS =========="
./gendocs || echo "Documentation generation failed, continuing build..."
echo "========== BUILD scanner + metadata_worker =========="
docker compose build --no-cache scanner metadata_worker
echo "========== RESTART scanner + metadata_worker =========="
docker compose up -d --force-recreate scanner metadata_worker
echo "========== HEALTH =========="
./health || true
echo "========== LOGS =========="
docker compose logs -f --tail=50 scanner metadata_worker
```

## `rebuildall`

Bouwt de volledige stack opnieuw.

- Bestaat: `True`
- Regels: `13`
- Gebruikt docker compose: `True`
- Gebruikt Redis: `False`

```bash
#!/bin/bash
set -e
cd /volume1/docker/nas-stack
echo "========== DOCS =========="
./gendocs || echo "Documentation generation failed, continuing build..."
echo "========== BUILD ALL =========="
docker compose build --no-cache
echo "========== RESTART ALL =========="
docker compose up -d --force-recreate --remove-orphans
echo "========== HEALTH =========="
./health || true
echo "========== LOGS =========="
docker compose logs -f --tail=50
```

## `logs`

Toont live logs.

- Bestaat: `True`
- Regels: `3`
- Gebruikt docker compose: `True`
- Gebruikt Redis: `False`

```bash
#!/bin/bash
cd /volume1/docker/nas-stack
docker compose logs -f --tail=50 scanner metadata_worker
```

## `status`

Toont status, locks, heartbeats en streaminfo.

- Bestaat: `True`
- Regels: `45`
- Gebruikt docker compose: `True`
- Gebruikt Redis: `True`

```bash
#!/bin/bash
cd /volume1/docker/nas-stack

echo "========== CONTAINERS =========="
docker compose ps

echo
echo "========== HEALTH =========="
docker inspect nas-scanner-1 --format 'scanner: {{if .State.Health}}{{.State.Health.Status}}{{else}}no healthcheck{{end}}' 2>/dev/null || true
docker inspect nas-metadata_worker-1 --format 'metadata_worker: {{if .State.Health}}{{.State.Health.Status}}{{else}}no healthcheck{{end}}' 2>/dev/null || true
docker inspect nas-redis-1 --format 'redis: {{if .State.Health}}{{.State.Health.Status}}{{else}}no healthcheck{{end}}' 2>/dev/null || true

echo
echo "========== HEARTBEATS =========="
echo -n "scanner: "
docker exec nas-redis-1 redis-cli GET scanner:heartbeat 2>/dev/null || true
echo -n "metadata_worker: "
docker exec nas-redis-1 redis-cli GET metadata_worker:heartbeat 2>/dev/null || true

echo
echo "========== LAST ACTIVITY =========="
echo -n "scanner:last_scan = "
docker exec nas-redis-1 redis-cli GET scanner:last_scan 2>/dev/null || true
echo -n "metadata_worker:last_event = "
docker exec nas-redis-1 redis-cli GET metadata_worker:last_event 2>/dev/null || true

echo
echo "========== LOCKS =========="
docker exec nas-redis-1 redis-cli KEYS "*lock*" 2>/dev/null || true

echo
echo "========== STREAM =========="
docker exec nas-redis-1 redis-cli XLEN scan_stream 2>/dev/null || true

echo
echo "========== GROUPS =========="
docker exec nas-redis-1 redis-cli XINFO GROUPS scan_stream 2>/dev/null || true

echo
echo "========== DLQ =========="
docker exec nas-redis-1 redis-cli XLEN scan_stream_dlq 2>/dev/null || true

echo
echo "========== DOCS =========="
ls -lh docs/DOCUMENTATIE.md 2>/dev/null || echo "docs/DOCUMENTATIE.md ontbreekt"
```

## `dlq`

Toont DLQ-informatie.

- Bestaat: `True`
- Regels: `7`
- Gebruikt docker compose: `False`
- Gebruikt Redis: `True`

```bash
#!/bin/bash
cd /volume1/docker/nas-stack
echo "========== DLQ LENGTH =========="
docker exec nas-redis-1 redis-cli XLEN scan_stream_dlq
echo
echo "========== LAST 20 DLQ ITEMS =========="
docker exec nas-redis-1 redis-cli XREVRANGE scan_stream_dlq + - COUNT 20
```

## `redis`

Opent redis-cli.

- Bestaat: `True`
- Regels: `2`
- Gebruikt docker compose: `False`
- Gebruikt Redis: `True`

```bash
#!/bin/bash
docker exec -it nas-redis-1 redis-cli
```

## `cleanlocks`

Verwijdert locks handmatig.

- Bestaat: `True`
- Regels: `6`
- Gebruikt docker compose: `False`
- Gebruikt Redis: `True`

```bash
#!/bin/bash
cd /volume1/docker/nas-stack
docker exec nas-redis-1 redis-cli DEL scanner:lock:event
docker exec nas-redis-1 redis-cli DEL metadata_worker:lock
docker exec nas-redis-1 redis-cli DEL metadata:lock
echo "Locks cleared."
```

## `watch`

Live monitor.

- Bestaat: `True`
- Regels: `3`
- Gebruikt docker compose: `True`
- Gebruikt Redis: `True`

```bash
#!/bin/bash
cd /volume1/docker/nas-stack
watch -n 5 'docker compose ps; echo; docker exec nas-redis-1 redis-cli XLEN scan_stream; echo; docker exec nas-redis-1 redis-cli XINFO GROUPS scan_stream; echo; docker exec nas-redis-1 redis-cli XLEN scan_stream_dlq'
```

## `gendocs`

Script

- Bestaat: `True`
- Regels: `5`
- Gebruikt docker compose: `False`
- Gebruikt Redis: `False`

```bash
#!/bin/bash
set -e

cd /volume1/docker/nas-stack
python3 tools/docs/generate_docs.py
```

