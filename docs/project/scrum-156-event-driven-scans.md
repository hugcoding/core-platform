# SCRUM-156 — Eventgestuurde scans en CORE Pulse-instellingen

## Gedrag

- De standaard periodieke incrementele polling staat uit.
- Watcher-events worden na een settleperiode samengevoegd tot veilige scopes.
- Een wijziging in `Persoonlijk/Actief/Werk/Sollicitaties` scant standaard
  `Persoonlijk/Actief/Werk`.
- Parent- en childscopes worden gededupliceerd.
- Scopes met minder dan drie segmenten onder de watchroot worden uitgesteld tot
  de volgende volledige scan.
- Een dirty scan verwerkt uitsluitend nieuwe of gewijzigde bestanden en voert
  geen missing/delete-reconciliatie uit.
- De volledige scan draait standaard om 02:30 in `Europe/Amsterdam`, binnen een
  venster van 30 minuten. Een herstart overdag start standaard geen gemiste scan.
- Een geslaagde volledige scan wist de uitgestelde scopes.

## CORE Pulse

Via **Instellingen** zijn planning, polling, scope, settleperiode en beleid voor
een gemiste scan aanpasbaar. Scanroots en watchroots zijn alleen-lezen. Opslaan
start nooit impliciet een scan. De knop **Volledige scan aanvragen** maakt een
idempotent Redis-verzoek dat de scanner bij zijn volgende cyclus consumeert.

De configuratie staat duurzaam in `public.scan_runtime_settings`. Iedere
wijziging wordt append-only vastgelegd in
`public.scan_runtime_settings_audit`. Redis bevat alleen de actieve runtime-
snapshot voor scanner en watcher.

## Uitrol

Voer eerst de migratie uit en bouw daarna dashboard, scanner en watcher opnieuw:

```bash
docker exec -i postgres psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test \
  < database/migrations/20260921_add_scan_runtime_settings.sql
docker compose up -d --no-deps --build dashboard scanner watcher
```

Rollback verwijdert uitsluitend de nieuwe configuratie- en audittabellen:

```bash
docker exec -i postgres psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test \
  < database/migrations/rollback/20260921_add_scan_runtime_settings.sql
```
