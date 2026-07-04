# ADR-0001 - Polling scanner in plaats van inotify

## Status

Accepted

## Context

De oorspronkelijke aanpak gebruikte inotify via een host watcher. Op Synology bleek dit kwetsbaar door kernelbeperkingen, bind-mountgedrag, losse hostprocessen en extra complexiteit met een Python-venv buiten Docker.

## Decision

We gebruiken een polling scanner binnen Docker. De scanner loopt periodiek door toegestane shares onder `/volume1`, vergelijkt file signatures en schrijft alleen wijzigingen naar Redis.

## Consequences

Positief:
- Geen host watcher meer.
- Geen aparte Python-venv op de NAS.
- Alles draait binnen Docker.
- Beter reproduceerbaar en beheerbaar.
- Minder afhankelijk van Synology-specifieke inotify-beperkingen.

Negatief:
- Polling gebruikt meer I/O dan pure event-based monitoring.
- Grote shares zorgen voor langere scanrondes.
- Performance-optimalisatie via batching en Redis pipelines wordt belangrijk.

## Alternatives considered

- Host-side inotify watcher.
- Container-side inotify.
- Periodieke full scan zonder signatures.
- Synology-specifieke indexeringshooks.

## Date

2026-06-27
