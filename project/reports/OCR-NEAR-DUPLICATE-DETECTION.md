# OCR-gebaseerde detectie van vrijwel identieke PDF's

## Doel en scope

CORE gebruikt deze route uitsluitend voor PDF-bestanden die geen byte-exact
duplicaat zijn, maar mogelijk hetzelfde document bevatten. De route is
bedoeld voor bijvoorbeeld een origineel en een gecomprimeerde, gescande of
licht afwijkende kopie.

De uitkomst is altijd een voorstel voor menselijke beoordeling onder
**Inhoudelijk vrijwel identieke pdf's**. CORE verwijdert, overschrijft,
verplaatst of accordeert hierbij nooit automatisch een bestand.

## Voorselectie

Een paar wordt alleen vergeleken wanneer:

- beide bestanden actuele, afgeronde OCR-artifacts hebben;
- beide actuele PDF-bestanden zijn;
- de binaire SHA-256-hashes verschillen;
- beide bestandsnamen dezelfde veilige genormaliseerde documentidentiteit
  opleveren, waarbij suffixen zoals `gecomprimeerd`, `signed`, `kopie` en
  versienummers gecontroleerd worden genegeerd;
- het specifieke paar met deze hashes nog niet eerder door dezelfde
  analyzerversie is onderzocht.

Per vrije achtergrondcyclus worden maximaal drie nog niet onderzochte paren
vergeleken. De bestaande OCR-worker pauzeert bij onderhoud, Redis-problemen,
databasebelasting, actieve gecontroleerde uitvoering, hoge NAS-load, weinig
beschikbaar geheugen of achterstand in de primaire CORE-pipeline.

## Beslisgrenzen

Een paar wordt alleen als waarschijnlijk inhoudelijk duplicaat aangeboden
als alle volgende voorwaarden gelijktijdig slagen:

| Signaal | Grens |
| --- | ---: |
| Genormaliseerde OCR-tekst per document | minimaal 500 tekens |
| Verhouding tussen tekstlengtes | minimaal 98% |
| Jaccard-overlap van unieke woorden | minimaal 95% |
| Jaccard-overlap van reeksen van vijf woorden | minimaal 90% |

De actuele analyzerversie is `ocr-near-duplicate-v1`. De uitvoer bevat de
gemeten scores en de gebruikte grenzen, maar geen geëxtraheerde documenttekst.

## Beoordeling en golden record

Een positieve vergelijking verschijnt in de bestaande PDF-gelijkenisreview.
De reviewer kan:

- één leidende kopie/golden record kiezen;
- de bestanden bewust apart bewaren;
- een eerder oordeel intrekken.

Een gekozen overbodige kopie wordt pas kandidaat voor quarantaine nadat het
menselijke oordeel append-only is opgeslagen. De daadwerkelijke verplaatsing
blijft een afzonderlijk goed te keuren gecontroleerde uitvoering.

Een digitale handtekening is geen reden om OCR-gelijkenis te verbergen. Het
ondertekende document wordt echter niet automatisch golden record; de reviewer
maakt die keuze expliciet.

## Bewijs en audit

`ocr_similarity_comparisons` registreert append-only:

- beide file-ID's en actuele contenthashes;
- genormaliseerde documentidentiteit;
- analyzerversie;
- alle scores en grenzen;
- of het paar kwalificeerde;
- tijdstip van vergelijking.

Ook negatieve vergelijkingen worden geregistreerd. Daardoor veroorzaakt een
niet-kwalificerend paar niet iedere idle-cyclus opnieuw CPU-belasting. OCR-tekst
blijft uitsluitend in het bestaande lokale gecomprimeerde artifact en wordt
niet in deze bewijstabel opgeslagen.

## Concrete validatie

Voor file-ID's `3363668` en `3363670` is gemeten:

- lengteverhouding: 99,91%;
- woordoverlap: 96,68%;
- vijfwoordvolgorde-overlap: 91,17%.

Dit paar passeert alle grenzen en wordt daarom na verwerking als menselijke
duplicaatreview aangeboden.

## Deployment

Na merge:

```bash
cd /volume1/docker/nas-stack
core git pull
docker exec -i postgres psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test \
  < database/migrations/20260916_allow_reviewed_ocr_near_duplicates.sql
docker compose up -d --no-deps --build dashboard workset_ocr_worker
```

Controleer vervolgens:

```sql
SELECT left_file_id, right_file_id, qualifies, metrics, analyzer_version, created_at
FROM public.ocr_similarity_comparisons
ORDER BY created_at DESC
LIMIT 20;
```

Positieve groepen zijn zichtbaar via:

```sql
SELECT group_key, available_documents, file_ids, latest_review_action
FROM public.v_pdf_content_similarity_groups
ORDER BY available_documents DESC, group_key;
```

## Rollback

Rollback verwijdert alleen de nieuwe vergelijkingstabel en herstelt de vorige
projectieregel voor ondertekende PDF's:

```bash
docker exec -i postgres psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test \
  < database/migrations/rollback/20260916_allow_reviewed_ocr_near_duplicates.sql
```

De rollback muteert of verwijdert geen bronbestanden. Reeds append-only
opgeslagen algemene PDF-reviewevents blijven onderdeel van de bestaande
reviewhistorie.
