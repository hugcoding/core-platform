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
