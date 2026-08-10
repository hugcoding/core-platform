# SCRUM-89 Active workset pilot

## Doel

De eerste actieve-werksetpilot selecteert read-only actuele documentkandidaten
uit de tijdelijke OneDrive-basis. De pilot verplaatst geen bestanden, schrijft
niet naar PostgreSQL en gebruikt geen LLM.

## Afbakening

- Bron: `/volume1/data/import/cloud/onedrive/current/Documenten`.
- Bestandstypen: `docx` en `xlsx`.
- Activiteitsvenster: configuration-driven, initieel negen kalendermaanden.
- Exacte duplicaten: maximaal één resultaat per persistente contentgroep.
- Representatie: het bestaande golden record, ook als dit buiten de importroot staat.
- Huidig activiteitssignaal: `modified_at_fs`, expliciet met lage confidence.

De policy staat in `project/policies/active-workset-v1.json`.

## Uitvoeren

```sh
core workset pilot --dry-run
```

Reproduceerbaar uitvoeren:

```sh
core workset pilot --as-of 2026-08-10T12:00:00+02:00 --dry-run
```

## Uitvoer

Onder `project/exports/active-workset/` verschijnen een volledige CSV, compacte
review-CSV, JSON, Markdown en de verwijzingen `active-workset-v1-latest.json` en
`active-workset-v1-latest.md`.

De review bevat volgens de policy maximaal twintig actieve kandidaten per
extensie, tien kandidaten net buiten het venster en vijf duplicaatgroepen. Een
bestand dat in meerdere steekproeven valt komt één keer voor met meerdere
reviewredenen.

## Tijdcontract

`files.created_at` wordt uitsluitend geëxporteerd als
`core_first_observed_at`. Dit is geen documentaanmaakdatum en telt niet mee als
activiteit.

| Status | Reden | Betekenis |
|---|---|---|
| `active_candidate` | `source_mtime_within_configured_window` | Voorlopig binnen venster; lage confidence |
| `inactive` | `no_qualifying_activity_within_configured_window` | Geen bruikbaar signaal binnen venster |
| `needs_review` | `missing_persisted_golden_record` | Integriteitsbewijs ontbreekt |
| `needs_review` | `invalid_source_modified_at` | Tijdsbewijs ontbreekt of ligt in de toekomst |

De output noemt `source_created_at`, `content_changed_at` en
`last_human_activity_at` bewust als ontbrekende evidence. Mtime wordt pas als
primair bewijs vervangen wanneer bronaanmaak, oud/nieuw hashbewijs of
Windows/SMB-activiteit beschikbaar is.

## Veiligheidsgrenzen

- Geen databasewrites of bestandsmutaties.
- Geen lifecycle- of doelpadwijzigingen.
- Geen classificatie of LLM-verwerking.
- Geen hardcoded termijn in reason-codes.
- Policywaarde en policyversie worden bij ieder resultaat vastgelegd.
