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

Prompt `scrum-85-personal-classification-v1` levert:

- `document_type`;
- `category`: `personal`, `administration`, `finance`, `home`, `work`, `study`,
  `projects` of `other`;
- `document_family` en maximaal vijf onderwerpen;
- `lifecycle`: `active_candidate`, `archive_candidate`, `needs_review` of
  `quarantine`;
- een relatief `suggested_path` onder de bijpassende zone `Active`, `Archive`,
  `Review` of `Quarantine`;
- `sensitivity`, `confidence` en `reason`.

Mutatiedatum mag lifecycle ondersteunen maar bepaalt nooit documenttype of
categorie. Een lifecycle en doelzone die elkaar tegenspreken, een onveilig pad,
een onbekende enum of ongeldige JSON wordt teruggebracht naar
`Review/Unclassified` met lage confidence.

## Vervolg

De JSON-, Markdown- en compacte CSV-uitvoer zijn reviewmateriaal. Pas na
menselijke beoordeling en een afzonderlijk go/no-go kan een copy/move-plan worden
ontworpen. Cleanup, archivering en retentie blijven aparte geautoriseerde stappen.
