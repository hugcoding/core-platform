# ADR-0001 - Hybride realtime events en polling-reconciliation

## Status

Superseded decision, opnieuw geaccepteerd op 2026-07-26.

## Context

CORE gebruikte oorspronkelijk uitsluitend een polling scanner. Dat was reproduceerbaar op Synology, maar veroorzaakte onnodige I/O en verwerkte normale wijzigingen pas tijdens een volgende scan. Een eerste watcherproef op heel `/volume1` liet bovendien zien dat het recursief registreren van alle legacy- en applicatiemappen te langzaam initialiseert.

## Decision

CORE gebruikt een hybride model:

- een containerized filesystem watcher verwerkt realtime events;
- de eerste goedgekeurde watchroot is `/volume1/data`;
- watcher-events gaan naar de prioriteitsstream `scan_stream_realtime`;
- de metadata-worker controleert realtime vóór kleine pollingbatches;
- geraakte roots worden als dirty gemarkeerd voor scoped reconciliation;
- de fallbackscan draait ieder uur;
- een volledige reconciliation draait eenmaal per 24 uur.

De watcher mount `/volume1` read-only en kan zelf geen bestanden wijzigen of verwijderen. Extra realtime roots worden alleen expliciet en gefaseerd via `WATCH_ROOTS` toegevoegd.

## Consequences

Positief:

- normale bestandsmutaties worden binnen enkele seconden verwerkt;
- een grote pollingscan blokkeert realtime events niet;
- polling blijft beschikbaar voor overflow, downtime en gemiste events;
- dirty-rootreconciliation veroorzaakt geen deletes buiten de geselecteerde scope;
- alle processen blijven reproduceerbaar in Docker.

Negatief:

- er zijn twee Redis Streams en drie runtimeprocessen om te bewaken;
- nieuwe watchroots vragen expliciete capaciteit- en acceptatietests;
- Synology Container Manager kan na recreatie met geopende GUI onjuiste ID-prefixen tonen.

## Alternatives considered

- uitsluitend polling;
- een host-side inotifyproces;
- heel `/volume1` direct realtime bewaken;
- Synology-specifieke indexeringshooks.

## Validation

De live acceptatietest op 2026-07-26 onder `/volume1/data` bewees:

- create: 2 seconden;
- modify: 2 seconden;
- rename: 4 seconden;
- move: 4 seconden;
- delete: 2 seconden.

Alle mutaties bleven op één `file_id` en werden met bron `filesystem_watcher` in `file_events` geregistreerd.
