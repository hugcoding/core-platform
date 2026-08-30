# SCRUM-116 controlled execution

Een menselijke selectie van maximaal 25 bestanden wordt immutable vastgelegd. De
`controlled_execution_worker` voert uitsluitend goedgekeurde batches uit en
gebruikt de bestaande geverifieerde move-primitives.

## Veiligheidscontract

- bron en doel liggen onder `/volume1/data`;
- doelzones zijn beperkt tot Persoonlijk Actief/Inactief of de toepasselijke quarantaine;
- bronformaat, SHA-256, vrije ruimte en doelcollision worden vóór uitvoering gecontroleerd;
- een exacte duplicate wordt alleen verplaatst als de behouden golden copy opnieuw is geverifieerd;
- na de move worden formaat, SHA-256 en filesystem-mtime opnieuw gecontroleerd;
- alle voortgang is append-only; classificaties en ruwe events worden niet gewijzigd;
- een onderbroken move blijft `started`, pauzeert de batch en kan veilig worden hervat;
- rollback verifieert opnieuw voordat het oorspronkelijke pad wordt hersteld;
- permanente verwijdering wordt niet ondersteund.

## Installatie

Voer de progressiemigratie eenmalig uit en bouw dashboard plus worker:

```bash
docker exec -i postgres psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test \
  < database/migrations/20260830_enhance_controlled_execution_progress.sql
docker compose up -d --no-deps --build dashboard controlled_execution_worker
```

## Bediening

Workset toont de actuele batch en ververst iedere drie seconden. Een operator kan
een batch pauzeren, hervatten en na pauzeren annuleren. Een voltooide of gedeeltelijk
mislukte batch met uitgevoerde moves kan rollback aanvragen. Pauzeren grijpt in
tussen bestanden; een lopende atomaire move wordt eerst veilig afgerond.

## Integratietest

De test bouwt een eigen PostgreSQL-container en volume, voert een echte move uit,
controleert databaseprogressie en voert daarna een echte rollback uit:

```bash
docker compose -f tests/integration/controlled-execution/compose.yml \
  up --build --abort-on-container-exit --exit-code-from integration
docker compose -f tests/integration/controlled-execution/compose.yml down -v
```

Dezelfde roundtrip draait als verplichte GitHub Actions-workflow bij relevante PR's.
