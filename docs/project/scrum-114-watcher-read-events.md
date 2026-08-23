# SCRUM-114 — openen is geen wijziging

Synology kan een filesystemmelding geven wanneer een document alleen wordt geopend en
gesloten. De watcher stuurde die melding als `UPSERT` door. De Metadata Worker maakte
daar voor ieder bestaand pad automatisch een `MODIFIED`-event van, ook wanneer grootte,
mtime en filesystem-identiteit exact gelijk waren gebleven.

CORE vergelijkt daarom voortaan eerst bestandsgrootte, filesystem-mtime,
filesystem/device-identiteit en inode. Zijn deze signalen allemaal gelijk en is geen
geforceerde metadataherbouw gevraagd, dan wordt de melding als niet-materieel genegeerd.
Echte writes, moves, renames en deletes blijven via de bestaande verwerking lopen.

## Historische correcties

Oorspronkelijke events worden niet verwijderd. De migratie voegt append-only
`file_event_corrections` toe. Alleen watcher-events waarvan de eventtijd aantoonbaar meer
dan vijf minuten na de onveranderde filesystem-mtime ligt, zijn kandidaat voor correctie.

```bash
core metadata correct-read-events --limit 100 --dry-run
```

Toepassen vereist een expliciete bevestiging:

```bash
core metadata correct-read-events --limit 100 --apply \
  --confirm INVALIDATE_NON_MATERIAL_WATCHER_EVENTS
```

De effectieve event-view sluit gecorrigeerde events uit. De originele auditregel en de
append-only correctie blijven beide bewaard.

Operationele lezers gebruiken deze effectieve historie: de Pulse-telling,
identiteits- en integriteitsanalyse en eventcorrelatie van persoonlijke migratie en
duplicate-quarantaine. Rechtstreeks lezen uit `file_events` is alleen bedoeld voor
auditonderzoek, nieuwe eventregistratie en de correctietool zelf.

## Watcher en scanner zien dezelfde verwijdering

De watcher registreert een verwijdering direct. De polling scanner controleert later
dezelfde opslag als herstelmechanisme en kan hetzelfde ontbrekende pad opnieuw melden.
De Metadata Worker maakt daarom alleen nog een `DELETED`-event wanneer het bestand in
de database nog niet als verwijderd staat. De scanner blijft wel actief als vangnet.

Historische dubbelen kunnen eerst read-only worden onderzocht:

```bash
core metadata correct-duplicate-deletes --limit 100 --dry-run
```

Toepassen vereist een afzonderlijke expliciete bevestiging:

```bash
core metadata correct-duplicate-deletes --limit 100 --apply \
  --confirm INVALIDATE_DUPLICATE_DELETE_OBSERVATIONS
```

Alleen een latere `polling_scanner`-delete met hetzelfde file-ID en bronpad als een
eerdere effectieve `filesystem_watcher`-delete komt in aanmerking. Een tussentijdse
`RESTORED`, `CREATED`, `MOVED` of `RENAMED` blokkeert correctie. De scanner-event blijft
ruw bewaard en krijgt append-only `duplicate_observation`-bewijs; alleen de effectieve
view sluit deze herhaalde waarneming uit.
