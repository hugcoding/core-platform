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
