# Troubleshooting

Alle runtime checks lopen via de CORE CLI. Run deze commands op de NAS in `/volume1/docker/nas-stack`, of via de Windows wrapper vanuit de repository.

## Worker is unhealthy

```bash
core runtime health
```

Voor detailinformatie:

```bash
docker inspect nas-metadata_worker-1 --format '{{json .State.Health}}'
```

Controleer of de healthcheck `python3` gebruikt.

## Scanner doet niets

```bash
core runtime logs
core runtime status
```

## Realtime watcher ontbreekt of is unhealthy

```bash
core runtime health
core runtime status
/usr/local/bin/docker compose logs --tail=200 watcher
```

Controleer in `core runtime status` de watcher-heartbeat, `watcher:last_event` en `scanner:dirty_roots`. Een ontbrekende heartbeat betekent dat de watcher niet actief is of Redis niet kan bereiken. Herstel eerst de watcher en laat de dirty-root reconciliation afronden voordat u een opschoning start.

## Container Manager toont een ID-prefix

Controleer de echte Dockernaam:

```bash
docker ps --format '{{.Names}}'
```

Als Docker `nas-scanner-1`, `nas-metadata_worker-1` en `nas-watcher-1` toont, is alleen de Synology-interface uit sync. Sluit Container Manager voordat containers met Compose worden gerecreëerd en open de GUI pas nadat de containers stabiel en gezond zijn.

## Worker zegt dat er al een worker draait

Controleer locks en heartbeats:

```bash
core runtime status
```

## DLQ groeit

```bash
core runtime dlq
```

## Noodoplossing locks

```bash
core runtime cleanlocks
```

## Live monitor

```bash
core runtime watch
```

## Windows wrapper

```powershell
.\tools\windows\core.ps1 runtime status
.\tools\windows\core.ps1 runtime dlq
```
