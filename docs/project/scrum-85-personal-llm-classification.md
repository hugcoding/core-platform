# SCRUM-85 Persoonlijke LLM-classificatie

## Doel

Deze pilot gebruikt een lokale LLM om controleerbare organisatievoorstellen te
maken voor persoonlijke OneDrive golden records. Het resultaat is advies voor
categorie, documentfamilie, lifecycle en doelpad. De pilot verplaatst, hernoemt,
archiveert of verwijdert niets.

## Grenzen

- Bron: standaard `/volume1/data/import/cloud/onedrive/current/Documenten`.
- Selectie: maximaal 25 recente persisted golden records met volledige SHA-256.
- Formaten: PDF en DOCX met lokaal extraheerbare tekst.
- Exacte contentgroep: maximaal één golden record.
- Verwerking: uitsluitend lokaal via de provider-onafhankelijke LLM-interface.
- Databasewrites en bestandsmutaties: uitgeschakeld.
- Elk voorstel heeft `needs_review=true`.

De eerdere embeddingpilot is geen toelatingseis. Een recent golden record zonder
semantic metadata kan lokaal worden geëxtraheerd en geclassificeerd. Padnamen
worden alleen gebruikt voor spreiding van de pilotselectie en als zwakke hint;
ze gelden nooit als classificatiewaarheid.

## Selectie controleren

Maak eerst uitsluitend het manifest en de compacte selectie-CSV:

```sh
core semantic personal-classification \
  --cutoff 2024-08-09T00:00:00+02:00 \
  --limit 25 \
  --dry-run
```

De round-robinselectie spreidt waar beschikbaar over administratie, financiën,
wonen, werk, studie, projecten en algemeen persoonlijk, en over PDF/DOCX en
groottes. Financiële, werk- en andere persoonlijke documenten mogen deelnemen,
omdat inhoud lokaal blijft. Duidelijke secretbestanden worden uitgesloten.

Ieder geselecteerd manifestitem start met:

```json
"approval": "pending_review"
```

Controleer de paden en wijzig elk item expliciet naar `approved` of `excluded`.
De classifier weigert een manifest zolang ook maar één `pending_review` resteert.
Minstens één document moet zijn goedgekeurd.

## Lokale classificatie uitvoeren

Na controle van het manifest:

```sh
core semantic personal-classification \
  --manifest project/exports/semantic-pilot/personal-golden-classification-manifest-YYYYMMDD-HHMMSS.json \
  --max-chunks 3 \
  --model qwen3.6:latest \
  --endpoint http://192.168.68.107:11434/v1 \
  --timeout-seconds 600
```

CORE extraheert per document maximaal drie gelijkmatig verdeelde chunks in de
bestaande offline semantic-container. De tekst wordt alleen in geheugen aan de
lokale LLM aangeboden en komt niet in rapport, CSV of database. Na ieder document
wordt een tijdelijk checkpoint geschreven, zodat bij een onderbreking reeds
verkregen voorstellen niet verloren gaan. Hervat met dezelfde selectieparameters
en `--resume project/exports/semantic-pilot/personal-golden-classification-checkpoint-....json`.

Vlak voor extractie vergelijkt CORE ieder goedgekeurd item opnieuw met de
operationele database. De volledige SHA-256, contentgroep, golden file-ID en het
bronpad moeten nog exact overeenkomen. Bij afwijking wordt de hele run geweigerd;
CORE vervangt of actualiseert nooit stil een beoordeeld document.

## Classificatiecontract

Prompt `scrum-85-personal-classification-v2` levert uitsluitend inhoudelijke
voorstellen:

- `document_type`;
- `category`: `personal`, `administration`, `finance`, `home`, `work`, `study`,
  `projects` of `other`;
- `document_family` en maximaal vijf onderwerpen;
- `lifecycle`: `active_candidate`, `archive_candidate`, `needs_review` of
  `quarantine`;
- `sensitivity` en expliciete `sensitivity_signals`;
- `confidence` en `reason`.

De LLM levert geen doelpad. CORE normaliseert categorie en documentfamilie,
verhoogt sensitivity wanneer beleidsregels dat vereisen, begrenst confidence bij
correcties en bouwt deterministisch:

```text
{Active|Archive|Review|Quarantine}/{Category}/{canonical_family}/{original_filename}
```

Voorbeelden van canonieke families zijn `curriculum_vitae`, `invoices`,
`income_tax`, `interview_preparation`, `vacancy_publications`, `diplomas`,
`certificates`, `vve_regulations` en `vve_technical_memos`. Hierdoor krijgen
inhoudelijk equivalente PDF- en DOCX-uitgaven dezelfde familie, onafhankelijk van
hoofdletters, taalvariant of vrije formulering van het model.

Mutatiedatum mag lifecycle ondersteunen maar bepaalt nooit documenttype of
categorie. Financiële, identiteits-, overheids-ID- en gezondheidsindicatoren
leggen een minimale sensitivity op. Bij categorie-, familie- of
sensitivitycorrecties wordt `high` confidence maximaal `medium`. Een onbekende
enum, ontbrekend sensitivitysignaal of ongeldige JSON wordt teruggebracht naar
`Review/Unclassified` met lage confidence.

Rapportage bewaart zowel `model_*`-waarden als de canonieke waarden en vermeldt
iedere correctie in `normalization_warnings`. Dit maakt het beleid controleerbaar
zonder het vrije modelvoorstel als operationele waarheid te behandelen.

## Vervolg

De JSON-, Markdown- en compacte CSV-uitvoer zijn reviewmateriaal. Pas na
menselijke beoordeling en een afzonderlijk go/no-go kan een copy/move-plan worden
ontworpen. Cleanup, archivering en retentie blijven aparte geautoriseerde stappen.

## ACC-opslag van voorstellen en reviews

De acceptatieomgeving kan classificaties versieerbaar opslaan zonder documenten
te muteren of geÃ«xtraheerde tekst te bewaren. De opslag gebruikt drie gescheiden
entiteiten:

- `classification_runs`: manifest-, prompt-, contract-, provider- en
  modelprovenance van een afgeronde lokale run;
- `classification_proposals`: canonieke machinevoorstellen met de bijbehorende
  contenthash en status `pending_review`;
- `classification_reviews`: append-only menselijke besluiten. Een review wordt
  nooit overschreven; een correctie is een nieuw besluit met een nieuwe
  `idempotency_key`.

`ai_output` wordt hiervoor niet hergebruikt. Die legacy-tabel mist het
classificatiecontract, reviewhistorie en voldoende lineage. Semantic extractie,
embeddings en classificatie blijven zo afzonderlijke processtappen.

Pas eerst de migratie toe op `nasdb_test`:

```sh
docker exec -i postgres psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test \
  < database/migrations/20260809_add_classification_acc_storage.sql
```

Maak daarna eerst een opslagplan van een afgerond v2-classificatierapport:

```sh
core semantic classification-acc proposals \
  project/exports/semantic-pilot/personal-golden-classification-YYYYMMDD-HHMMSS.json \
  --dry-run
```

Controleer het JSON-plan. Met exact dezelfde invoer ontstaat dezelfde run-ID,
proposal-ID en proposalhash. Opslaan in ACC gebeurt pas expliciet:

```sh
core semantic classification-acc proposals \
  project/exports/semantic-pilot/personal-golden-classification-YYYYMMDD-HHMMSS.json \
  --apply
```

De transactie weigert een voorstel wanneer file-ID, volledige SHA-256,
contentgroep en huidig golden record niet meer overeenkomen. Opnieuw uitvoeren
is idempotent. Een gelijk gebleven deterministische ID met een afwijkende
proposalhash wordt als provenancefout geweigerd.

Een geaccepteerde menselijke review gebruikt bijvoorbeeld:

```json
{
  "proposal_id": "00000000-0000-0000-0000-000000000000",
  "idempotency_key": "hugo-review-3361755-v1",
  "decision": "accepted",
  "reviewer": "hugo",
  "reviewed_at": "2026-08-09T13:00:00+02:00",
  "category": "administration",
  "document_family": "government_correspondence",
  "lifecycle": "active_candidate",
  "suggested_path": "Active/Administration/government_correspondence/brief.pdf",
  "sensitivity": "personal",
  "confidence": "medium",
  "notes": "Inhoud en doelpad beoordeeld"
}
```

Ook reviews doorlopen eerst `--dry-run` en daarna optioneel `--apply`:

```sh
core semantic classification-acc review review.json --dry-run
core semantic classification-acc review review.json --apply
```

`v_current_file_classification` toont maximaal Ã©Ã©n nieuwste geaccepteerd besluit
per bestand, en alleen zolang het bestand actief, nog het golden record en qua
contenthash ongewijzigd is. Pending en afgewezen voorstellen worden nooit als
huidige classificatie gepubliceerd. Controleer bijvoorbeeld:

```sql
SELECT file_id, category, document_family, lifecycle, suggested_path,
       sensitivity, confidence, reviewer, reviewed_at
FROM v_current_file_classification
ORDER BY reviewed_at DESC;
```

Rollback is alleen bedoeld voor ACC en verwijdert de view en alle drie de nieuwe
tabellen inclusief reviewhistorie:

```sh
docker exec -i postgres psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test \
  < database/migrations/rollback/20260809_add_classification_acc_storage.sql
```
