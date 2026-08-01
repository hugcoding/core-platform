# SCRUM-59 OneDrive golden semantic pilot

Deze pilot maakt een kleine, reproduceerbare documentset voor lokale extractie en
chunkplanning. De stap is read-only en geeft nog **geen** toestemming voor een
embeddingmodel, externe AI-dienst of databaseopslag.

## Selectiecontract

Een bestand komt alleen in het manifest wanneer het:

- actief onder `/volume1/data/import/cloud/onedrive/current` staat;
- het persisted golden record van een exacte inhoudsgroep is;
- een volledige SHA-256 heeft en niet leeg is;
- `.pdf` of `.docx` is;
- op of na de opgegeven filesystem-mutatiedatum is gewijzigd;
- niet door de conservatieve padfilter als gevoelig wordt herkend;
- binnen de expliciete pilotlimiet valt.

De mutatiedatum beperkt alleen de recente pilotscope. Zij bepaalt nooit welk
bestand golden record is. Eén exacte inhoudsgroep levert hoogstens één document.

## Stap 1: manifest en review

```sh
core semantic onedrive-golden-pilot \
  --cutoff 2024-08-01T00:00:00+02:00 \
  --limit 50 \
  --dry-run
```

De uitvoer komt in `project/exports/semantic-pilot/` en bevat:

- een JSON-manifest voor de geïsoleerde pilotcontainers;
- een CSV met geselecteerde en uitgesloten kandidaten plus reden;
- een Markdownrapport met alleen aggregaten.

Het manifest zet `embedding_enabled`, `external_ai_enabled` en
`database_writes_enabled` expliciet op `false`. Er wordt geen geëxtraheerde tekst
in manifest, review of rapport opgeslagen.

## Stap 2: lokale extractiecontrole

```sh
core semantic pilot-extract \
  project/exports/semantic-pilot/onedrive-golden-pilot-YYYYMMDD-HHMMSS.json
```

De container heeft geen netwerk, draait read-only en mount `/volume1` read-only.
De uitvoer bevat alleen statistieken zoals woorden, pagina's en extractiestatus.

## Stap 3: lokale chunkplanning

```sh
core semantic pilot-chunks \
  project/exports/semantic-pilot/onedrive-golden-pilot-YYYYMMDD-HHMMSS.json
```

Chunkidentiteiten zijn deterministisch gebaseerd op bestand, inhoudsversie,
volgnummer en chunkhash. De uitvoer bevat geen chunktekst en schrijft niets naar
PostgreSQL. Een vervolg met echte embeddings vereist eerst expliciete goedkeuring
van de SCRUM-57 architectuurreview.

## Veiligheidsgrenzen

- Geen mutaties aan bestanden, golden records of database.
- Geen vectoren of embeddings.
- Geen externe AI of netwerktoegang.
- Geen gevoelige documenten in deze pilot.
- Geen autonome classificatie-, cleanup- of verwijderactie.
