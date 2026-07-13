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

## Docs build op NAS zegt dat MkDocs ontbreekt

Controleer eerst of MkDocs op dezelfde machine staat als waar je `core docs build` draait:

```bash
python3 -m mkdocs --version
```

Als MkDocs ontbreekt op de NAS:

```bash
python3 -m pip install --user mkdocs-material
core docs build
```

CORE probeert eerst `mkdocs` op `PATH` en valt daarna terug op `python3 -m mkdocs`.

## `core` niet herkend in Windows PowerShell

Gebruik de Windows wrapper vanuit de repository:

```powershell
.\tools\windows\core.ps1 docs build
```

Of voeg een Windows `core` wrapper toe aan je PATH.

## Docker command gebruikt Docker Desktop in plaats van NAS

Als je in Windows PowerShell `docker ...` draait, praat je met Docker Desktop. Gebruik voor NAS Docker commands SSH of draai het command direct op de NAS:

```powershell
ssh hugo@NAS "cd /volume1/docker/nas-stack && docker compose ps"
```

## Bash prompt blijft hangen op `>`

Er staat waarschijnlijk een open quote in je command. Druk `Ctrl+C` en voer het command opnieuw uit zonder los afsluitend aanhalingsteken.

PowerShell gebruikt geen Bash line continuation met `\`. Gebruik lange NAS databasecommands bij voorkeur als een enkele SSH-regel, of voer losse Bash-regels direct op de NAS uit.

