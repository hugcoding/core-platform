# SCRUM-59 OneDrive golden semantic pilot

Deze pilot maakt een kleine, reproduceerbare documentset voor lokale extractie,
chunkplanning en een begrensde lokale embeddingbenchmark. Externe AI blijft
uitgeschakeld. In ACC mag uitsluitend reproduceerbare technische metadata worden
opgeslagen; bronbestanden blijven read-only.

## Selectiecontract

Een bestand komt alleen in het manifest wanneer het:

- actief onder `/volume1/data/import/cloud/onedrive/current` staat;
- het persisted golden record van een exacte inhoudsgroep is;
- een volledige SHA-256 heeft en niet leeg is;
- `.pdf` of `.docx` is;
- op of na de opgegeven filesystem-mutatiedatum is gewijzigd;
- niet door de conservatieve padfilter als gevoelig wordt herkend;
- binnen de expliciete pilotlimiet valt.

De privacyfilter groepeert padbewijs voor secrets, identiteit, financiën,
gezondheid, werk/sollicitatie en persoonlijke documenten. Dit is een
voorzorgsfilter voor de lokale pilot en geen definitieve inhoudsclassificatie.

Geschikte kandidaten worden deterministisch om-en-om gekozen uit `study`,
`work`, `administration` en `general`. Zo wordt de limiet niet volledig gevuld
door één map met de nieuwste documenten. Een categorie die onvoldoende veilige
kandidaten heeft, blokkeert de andere categorieën niet.

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

Het rapport telt een niet-ondersteund bestandstype als `unsupported_extension`
voordat de hashstatus wordt beoordeeld. `missing_full_sha256` betreft daardoor
alleen PDF/DOCX-kandidaten die de extractiepilot werkelijk zou kunnen gebruiken.

Een document-hash-backfill krijgt na toepassing van de bijbehorende migratie een
eigen `scan_sessions`-record van type `hash_backfill`. De scanner koppelt ieder
werkitem aan die sessie, zodat gepland en verwerkt zichtbaar worden naast full-
en intervalscans.

## Stap 2: lokale extractiecontrole

```sh
core semantic pilot-extract \
  project/exports/semantic-pilot/onedrive-golden-pilot-YYYYMMDD-HHMMSS.json
```

De container heeft geen netwerk, draait read-only en mount `/volume1` read-only.
De uitvoer bevat alleen statistieken zoals woorden, pagina's en extractiestatus.
De container bevat lokale cryptografische ondersteuning om AES-PDF's met een
lege gebruikerswachtwoordlaag veilig te openen. Een werkelijk met een wachtwoord
beveiligde PDF blijft geblokkeerd en wordt als `password_protected` gerapporteerd;
CORE probeert geen wachtwoorden te raden of op te slaan.

Na de individuele regels volgt één JSON-samenvatting met aantallen voor
`extracted`, `extractable_text`, `needs_ocr`, `no_text`, `password_protected`,
`skipped` en `errors`, plus totale woorden, tekens en PDF-pagina's. Ook deze
samenvatting bevat geen documenttekst.

## Stap 3: lokale chunkplanning

```sh
core semantic pilot-chunks \
  project/exports/semantic-pilot/onedrive-golden-pilot-YYYYMMDD-HHMMSS.json
```

Chunkidentiteiten zijn deterministisch gebaseerd op bestand, inhoudsversie,
volgnummer en chunkhash. De uitvoer bevat geen chunktekst en schrijft niets naar
PostgreSQL. Een vervolg met echte embeddings vereist eerst expliciete goedkeuring
van de SCRUM-57 architectuurreview.

## ACC-opslag voor technische metadata

Na toepassing van `database/migrations/20260801_add_semantic_acc_metadata.sql`
kan dezelfde lokale planning worden voorbereid voor de acceptatiedatabase:

```sh
core semantic acc-metadata \
  project/exports/semantic-pilot/onedrive-golden-pilot-YYYYMMDD-HHMMSS.json \
  --dry-run
```

De dry-run maakt een controleerbaar JSON-plan maar schrijft niets. Na review kan
exact hetzelfde manifest expliciet worden toegepast:

```sh
core semantic acc-metadata \
  project/exports/semantic-pilot/onedrive-golden-pilot-YYYYMMDD-HHMMSS.json \
  --apply
```

De deterministische run-id is gebaseerd op manifesthash, extractorversie en
chunkerversie. Unieke sleutels en upserts maken herhalen idempotent. Voor ieder
document valideert de transactie opnieuw de volledige inhoudshash en dat het
bestand nog het persisted golden record is. Bij afwijking rolt de hele transactie
terug.

Opgeslagen worden runstatus, versies, `file_id`, `content_group_id`, hash,
extractiestatistieken, OCR/passwordstatus en per chunk alleen identiteit,
volgnummer en afmetingen. Ruwe tekst en embeddings worden niet opgeslagen.

## Golden/semantic databaseview

Migratie `database/migrations/20260802_add_semantic_golden_records_view.sql`
beheert `public.v_semantic_golden_records`. De view bevat per actief golden record
het aantal exacte kopieÃ«n en de nieuwste semantic-documentrun. De afgeleide
kolom `semantic_readiness` onderscheidt onder meer `not_processed`, `ready`,
`stale` en `stale_content_group`; `semantic_metadata_current` is alleen waar als
hash, contentgroep en geplande status nog overeenkomen.

De migratie gebruikt `CREATE OR REPLACE VIEW` en is daardoor ook toepasbaar als
de view eerder handmatig in ACC is aangemaakt. Rollback verwijdert alleen deze
view en haar twee ondersteunende indexen:

```sh
docker exec -i postgres psql -U hugo -d nasdb_test \
  < database/migrations/20260802_add_semantic_golden_records_view.sql
```

Rollback, alleen indien nodig:

```sh
docker exec -i postgres psql -U hugo -d nasdb_test \
  < database/migrations/rollback/20260802_add_semantic_golden_records_view.sql
```

## Lokale embeddingbenchmark in ACC

De eerste CPU-baseline gebruikt de vastgezette revisie van
`intfloat/multilingual-e5-small` (384 dimensies). Modeldownload en inference zijn
bewust gescheiden. Alleen deze expliciete stap gebruikt internet:

```sh
core semantic model-fetch
```

Bouw na een code- of dependencywijziging expliciet het CPU-only benchmarkimage:

```sh
core semantic benchmark-build
```

Een gewone benchmark bouwt het image niet opnieuw. Daarmee blijft de stap snel
en wordt niet bij iedere meting opnieuw een Docker-buildcontext verstuurd. De
`.dockerignore` sluit lokale modellen, exports, Git-data en gebouwde documentatie
uit van die context.

Daarna draait inference zonder netwerk, met read-only mounts voor het model en
`/volume1`:

```sh
core semantic embedding-benchmark \
  project/exports/semantic-pilot/onedrive-golden-pilot-YYYYMMDD-HHMMSS.json \
  --max-chunks 32 --batch-size 4
```

Het resultaat bevat alleen aggregaten: model en revisie, dimensie, aantallen,
doorvoer, piekgeheugen, geschatte vectoromvang en het aantal chunks dat boven de
modelcontext uitkomt. Extractietekst bestaat alleen tijdelijk in het geheugen;
tekst en vectoren worden niet gelogd, opgeslagen of naar PostgreSQL geschreven.
De benchmark verandert evenmin `semantic_runs`, `semantic_documents` of
`semantic_chunks`.

## Eerste benchmark en refinement

De eerste ACC-meting op 2 augustus 2026 verwerkte 32 chunks uit 19 documenten:

| Metriek | Resultaat |
|---|---:|
| Model | `intfloat/multilingual-e5-small` |
| Dimensie | 384 |
| Batch size | 4 |
| Model laden | 8,474 seconden |
| Embeddingtijd | 73,194 seconden |
| Doorvoer | 0,437 chunks/seconde |
| Piekgeheugen | 1.142,1 MiB |
| Tijdelijke float32-vectoromvang | 49.152 bytes |
| Truncated chunks | 20 van 32 |

De meting bewees dat de bestaande woordchunker van maximaal 600 woorden niet
past bij de modelcontext van 512 tokens. Woorden en modeltokens zijn niet
uitwisselbaar. Daarom gebruikt de embeddingbenchmark vanaf
`e5-tokens-384-overlap-64-v1` de tokenizer van exact de vastgezette modelrevision:

- doelgrootte 384 inhoudstokens;
- overlap 64 tokens;
- het verplichte E5-prefix `passage:` wordt daarna toegevoegd;
- de uiteindelijke modelinput wordt opnieuw geteld inclusief speciale tokens;
- iedere input boven de modelgrens stopt de benchmark vóór inference;
- stille truncation is niet toegestaan.

Dit verandert de bestaande `words-600-overlap-75-v1` ACC-run niet. Een nieuwe
tokenchunker is een nieuwe afgeleide versie en mag oudere metadata niet stil
overschrijven. Na deployment moet dezelfde 32-chunkbenchmark opnieuw worden
uitgevoerd. De acceptatiegrens is `truncated_chunks = 0`; daarna volgen metingen
met batch sizes 1, 2, 4 en eventueel 8.

Gebruik voor die vergelijking één matrixrun. Het model wordt één keer geladen en
dezelfde voorbereide chunks worden voor iedere batchgrootte gebruikt:

```sh
core semantic embedding-benchmark \
  project/exports/semantic-pilot/onedrive-golden-pilot-YYYYMMDD-HHMMSS.json \
  --max-chunks 32 --batch-sizes 1,2,4,8
```

De JSON-uitvoer bevat per batchgrootte de embeddingtijd en doorvoer, plus
`fastest_batch_size` en het globale piekgeheugen. De voor-tokenisatie van een
volledig document gebruikt stille tokenizerdiagnostiek; alleen een overschrijding
in de uiteindelijke modelinput is een blokkerende fout.

De matrixmeting van 2 augustus 2026 koos batch size 4 als ACC-default. De
doorvoer was 0,701 chunks/seconde voor 32 chunks, zonder truncatie en met een
piekgeheugen van 896,6 MiB. Batch size 2 presteerde vrijwel gelijk; batch size 8
was trager. Deze default is een gemeten instelling voor de huidige NAS en geen
algemene modeleigenschap.

De eerste containerbuild trok daarnaast een volledige CUDA/NVIDIA-stack binnen
en verstuurde 1,695 GB buildcontext. De benchmark heeft geen GPU nodig. Het
benchmarkimage installeert daarom expliciet de CPU-wheel van PyTorch en gebruikt
een kleine `.dockerignore`-context.

## Begrensde embeddingopslag in ACC

De legacy tabel `embeddings` gebruikt vectoren met 1.536 dimensies en wordt niet
hergebruikt voor het 384-dimensionale E5-model. De additive migratie maakt
afzonderlijke, versieerbare ACC-tabellen:

- `semantic_embedding_runs` voor model-, chunker- en runlineage;
- `semantic_embeddings_acc` voor tokenchunkmetadata en `vector(384)`;
- geen ruwe extractietekst in PostgreSQL;
- een foreign key naar de bestaande semantic document-run;
- een deterministisch run-ID en idempotente inserts.

Pas eerst de migratie toe:

```sh
docker exec -i postgres psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test \
  < database/migrations/20260802_add_semantic_embeddings_acc.sql
```

Maak daarna altijd eerst een begrensd plan. Inference blijft lokaal, offline en
read-only; alleen het afgeleide plan met vectoren wordt als auditexport bewaard:

```sh
core semantic embedding-acc \
  project/exports/semantic-pilot/onedrive-golden-pilot-YYYYMMDD-HHMMSS.json \
  --max-chunks 32 --batch-size 4 --dry-run
```

Controleer `semantic_run_id`, aantallen, fouten en het planpad. Schrijf pas na
die controle naar ACC:

```sh
core semantic embedding-acc \
  project/exports/semantic-pilot/onedrive-golden-pilot-YYYYMMDD-HHMMSS.json \
  --max-chunks 32 --batch-size 4 --apply
```

`--apply` schrijft uitsluitend naar `nasdb_test`. De database valideert dat de
semantic run en golden-documentkoppeling al bestaan. Een gewijzigde contenthash,
onbekend bestand, verkeerde vectordimensie of afwijkend aantal chunks blokkeert
de transactie. De rollback verwijdert alleen de nieuwe ACC-tabellen.

## Read-only similarity retrieval

Na een toegepaste embedding-run kan CORE lokaal zoeken in dezelfde vastgezette
E5-vectorruimte. De retrieval schrijft niets naar PostgreSQL en retourneert
alleen actuele golden records waarvan `file_id`, `semantic_run_id`, modelrevision
en tokenchunker overeenkomen. Oude embeddings worden daardoor niet stil onder
nieuwere semantic metadata getoond.

Vrije tekst wordt lokaal met het verplichte E5-prefix `query:` omgezet naar een
vector. De query verlaat de NAS niet en wordt niet door CORE opgeslagen:

```sh
core semantic similarity query "golden records en documentbeheer" \
  --limit 10 --threshold 0.50
```

De optionele hybride ranking combineert de embedding score voor 85% met een
deterministische filename/path-termdekking voor 15%. Alleen de filename en de
laatste drie padsegmenten tellen mee; gedeelde opslag- en importprefixen zoals
`/volume1/data/import/cloud/onedrive/current` worden uitgesloten. Stopwoorden en
termen korter dan drie tekens tellen niet mee. De output houdt `similarity`,
`lexical_similarity` en `ranking_score` afzonderlijk zichtbaar:

```sh
core semantic similarity query "Python programmeren en data science" \
  --ranking hybrid --limit 10 --threshold 0.40
```

Een bestaand golden document kan eveneens als bron worden gebruikt. CORE neemt
dan per kandidaat de beste cosine-overeenkomst tussen bron- en doelchunks:

```sh
core semantic similarity document 3361606 \
  --limit 10 --threshold 0.50
```

Het resultaat bevat het golden pad, contentgroep, exact-copy-count, semantic
runlineage, matched chunk en een cosine similarity. Die similarity is alleen een
rangschikkingssignaal. Het is geen classificatieconfidence, duplicatebesluit,
golden-recordbesluit of toestemming voor cleanup. Met slechts 32 pilotchunks is
de recall bovendien bewust beperkt tot de huidige ACC-pilotset.

### Versieerbare retrieval-evaluatie

`project/pilots/scrum-59-retrieval-evaluation-v1.json` bevat vijf handmatig te
reviewen zoekvragen met verwachte en expliciet irrelevante file-ID's uit de
huidige pilot. De configuratie is testdata: zij traint het model niet en verandert
geen databasegegevens.

```sh
core semantic retrieval-evaluate \
  project/pilots/scrum-59-retrieval-evaluation-v1.json
```

Het model wordt eenmaal geladen en alle queryvectoren worden lokaal in één batch
gemaakt. Daarna vergelijkt de evaluator `embedding-v1` en `hybrid-v1` met:

- Hit@1, Hit@3 en Hit@10;
- mean reciprocal rank (MRR);
- expliciet irrelevante documenten in de top 3;
- de rang van het eerste verwachte document per zoekvraag.

JSON- en Markdownrapporten komen onder `project/exports/semantic-pilot/`. De
queries of meetresultaten worden niet in PostgreSQL geschreven. Bij uitbreiding
van de corpusset moeten verwachte file-ID's handmatig worden gereviewd; metrics
op een verkeerd labelbestand geven slechts schijnkwaliteit.

### Retrieval-evaluatie v2: families en graded relevance

De v1-config blijft ondersteund voor reproduceerbaarheid. Nieuwe reviews gebruiken
`project/pilots/scrum-59-retrieval-evaluation-v2.json`. Deze configuratie kan
file-ID's groeperen tot herbruikbare documentfamilies, zoals alle beoordeelde
payrolldocumenten of SQL-trainingen. Een testvraag hoeft daardoor niet langer
één willekeurige maand of documentversie als enige juiste uitkomst te behandelen.

Per vraag worden vier expliciete judgments gebruikt:

- `relevant`: direct bruikbaar antwoord (gain 2);
- `related`: inhoudelijk bruikbare context (gain 1);
- `hard_negative`: lijkt door termen of context passend, maar is inhoudelijk fout;
- `irrelevant`: handmatig beoordeeld als niet bruikbaar.

Resultaten zonder judgment blijven `unjudged`; ze worden niet stil als handmatig
irrelevant gepresenteerd. De evaluator rapporteert naast Hit@k en MRR ook
NDCG@10. Deze metriek beloont relevante documenten boven related documenten en
weegt hoge posities zwaarder. Hard negatives en expliciet irrelevante treffers
in de top 3 blijven afzonderlijk zichtbaar.

```sh
core semantic retrieval-evaluate \
  project/pilots/scrum-59-retrieval-evaluation-v2.json \
  --review-csv project/exports/semantic-pilot/semantic-retrieval-top3-review-compact-20260808.csv
```

Met een compacte review rapporteert CORE NDCG@3 en menselijke reviewdekking
voor de top 3. NDCG@10 blijft expliciet voorlopig zolang posities 4–10 niet
volledig zijn beoordeeld. Dit voorkomt dat onbeoordeelde resultaten stil als
irrelevant worden beschouwd bij het go/no-go voor de lokale LLM/RAG-pilot.

Naast JSON en Markdown ontstaat een Excel-vriendelijke UTF-8-CSV met voor iedere
ranking en zoekvraag de top 10. Beoordeel daarin vooral regels met een lege
`review_judgment`. Vul uitsluitend `review_judgment`, `document_family` en
`reviewer_notes` aan; behoud file-ID, ranking en score als auditcontext.

Toegestane judgments zijn `relevant`, `related`, `hard_negative` en
`irrelevant`. De kolom `proposed_judgment` is alleen een startvoorstel en geen
ground truth. Zo wordt de evaluatieset eerst inhoudelijk gecorrigeerd voordat
model, chunking of hybride gewichten worden bijgesteld. Ook v2 is volledig
read-only: er worden geen queries, judgments of resultaten naar PostgreSQL
geschreven.

## Representatieve pilot van maximaal 100 documenten

De tweede pilotselectie gebruikt `onedrive-golden-representative-v2`. Zij blijft
read-only en selecteert maximaal 100 recente, actuele OneDrive golden records.
De deterministische round-robin verdeelt kandidaten over:

- `study`, `work`, `project`, `administration` en `general`;
- PDF en DOCX;
- `small` (< 256 KiB), `medium` (< 2 MiB) en `large`.

De bestaande eisen voor recency, volledige SHA-256, persisted golden status,
ondersteund formaat en conservatieve gevoeligheidsuitsluiting blijven gelden.
Mutatiedatum begrenst alleen het pilotcorpus en bepaalt nooit het golden record.

Reviewmoment 1 genereert alleen manifest, rapport en CSV:

```sh
core semantic representative-pilot \
  --cutoff 2024-08-03T00:00:00+02:00 \
  --limit 100 \
  --dry-run
```

Na inhoudelijke goedkeuring wordt eerst semantic metadata toegepast. De lokale
embeddingstap gebruikt vervolgens maximaal drie tokenchunks per document. Bij
lange documenten worden begin, midden en einde gelijkmatig gekozen. De globale
hard limit blijft expliciet 300:

```sh
core semantic embedding-acc MANIFEST_JSON \
  --max-documents 100 \
  --max-chunks-per-document 3 \
  --max-chunks 300 \
  --batch-size 4 \
  --dry-run
```

Een manifest met meer dan 100 goedgekeurde documenten of een resultaat boven de
300 chunks wordt geweigerd in plaats van stil afgekapt. Extractiefouten blijven
zichtbaar als fouttelling; veiligheidslimieten worden niet als extractiefout
weggeschreven.

De retrieval-evaluatieset bevat vanaf deze pilot 15 vragen: vijf bestaande
baselinevragen, vijf semantische parafrases zonder directe filenametermen en vijf
hard-negativevragen. De verwachte file-ID's zijn testlabels en moeten bij iedere
corpusuitbreiding handmatig worden gecontroleerd.

## Plaats in de CORE-flow

```text
Bronbestanden
  -> scanner/watcher
  -> files, events en volledige hashes
  -> exacte content groups
  -> persisted golden record
  -> lokale extractie
  -> versieerbare tokenchunking
  -> lokale embeddings
  -> toekomstige vectorindex en retrieval
  -> toekomstig classificatie- of AI-voorstel
  -> menselijke review
  -> retentie, archief of cleanup
```

Golden-recordselectie, classificatieconfidence en semantic similarity blijven
afzonderlijke bewijslagen. Embeddings ondersteunen retrieval en vergelijking,
maar geven geen autonome toestemming voor een golden-wijziging, doelpad,
bewaartermijn of verwijderactie. Een toekomstige lokale LLM mag voorstellen
formuleren op opgehaalde broncontext; menselijke review blijft leidend bij
risicovolle acties.

## Veiligheidsgrenzen

- Geen mutaties aan bestanden of golden records.
- Alleen expliciet toegepaste, reproduceerbare technische metadata in ACC.
- Benchmarkvectoren bestaan uitsluitend tijdelijk in geheugen.
- Geen externe AI; benchmark-inference heeft geen netwerktoegang.
- Geen gevoelige documenten in deze pilot.
- Geen autonome classificatie-, cleanup- of verwijderactie.
