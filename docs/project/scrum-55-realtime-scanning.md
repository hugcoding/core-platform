# SCRUM-55 - Realtime scanning en reconciliation

## Resultaat

CORE verwerkt wijzigingen onder `/volume1/data` nu realtime. Polling blijft actief als betrouwbaar vangnet en voor roots die nog niet expliciet voor realtime bewaking zijn goedgekeurd.

## Architectuur

```text
filesystem event
    -> watcher
    -> scan_stream_realtime
    -> metadata_worker
    -> files + file_events

dirty root
    -> scoped interval reconciliation

daily schedule
    -> full reconciliation
```

De metadata-worker controleert `scan_stream_realtime` vóór iedere batch van maximaal tien berichten uit `scan_stream`. Hierdoor wordt realtime verwerking niet geblokkeerd door duizenden jobs van een full scan.

## Live configuratie

```text
WATCH_ROOTS=/volume1/data
WATCHER_DEBOUNCE_SECONDS=2
SCAN_INTERVAL=3600
FULL_SCAN_INTERVAL=86400
```

De watcher heeft een read-only mount van `/volume1`. De eerste scope is bewust beperkt tot de canonieke doelroot. Legacy-, applicatie- en mediaroots blijven via polling geïnventariseerd totdat ze afzonderlijk zijn beoordeeld.

## Acceptatietest 2026-07-26

De test is uitgevoerd terwijl de pollingstream nog duizenden achtergrondjobs bevatte.

| Mutatie | Verwerkingstijd |
|---|---:|
| Create | 2 seconden |
| Modify | 2 seconden |
| Rename | 4 seconden |
| Move | 4 seconden |
| Delete | 2 seconden |

De volledige auditketen gebruikte één `file_id`:

```text
CREATED
MODIFIED
RENAMED + IDENTITY_MATCHED
MOVED + IDENTITY_MATCHED
DELETED
```

Alle events hadden `source=filesystem_watcher`. Rename en move zijn met high-confidence identity matching automatisch gekoppeld; er zijn geen duplicaatrecords ontstaan.

Na de test zijn de tijdelijke mappen, het testrecord, één metadatarecord, zeven testevents en vier eerder ontstane test-DLQ-items gecontroleerd verwijderd. De DLQ eindigde op nul.

## Beheer

```bash
core runtime health
core runtime status
docker compose logs --tail=100 watcher metadata_worker scanner
```

Belangrijke Redis-status:

```text
watcher:heartbeat
watcher:heartbeat:status
watcher:last_event
scanner:dirty_roots
scan_stream_realtime
scan_stream
scan_stream_dlq
```

Bij containerrecreatie kunnen oude locks kort zichtbaar blijven. Verwijder locks alleen nadat is vastgesteld dat de genoemde oude container-ID niet meer bestaat. Normaal verlopen ze vanzelf.

## Synology Container Manager

Container Manager kan een oude container-ID als prefix tonen wanneer Compose containers worden gerecreëerd terwijl de GUI geopend is. Docker behoudt in dat geval wel de juiste naam.

Werkprocedure:

1. sluit Container Manager;
2. voer `docker compose build` en `docker compose up -d --force-recreate` uit;
3. wacht tot health en locks stabiel zijn;
4. open Container Manager opnieuw.

Controleer de echte namen met:

```bash
docker ps --format '{{.Names}}'
```

## Vervolg

- watcher-overflow expliciet detecteren en meten;
- extra watchroots alleen gefaseerd toelaten;
- handmatige pathscan via CORE CLI afronden;
- de langetermijngroei en retentie van beide Redis Streams beheren;
- daarna legacyreconciliation en consolidatie richting `/volume1/data`.
