# SCRUM-76 — OneDrive-baseline en golden-recordreview

!!! warning "Conceptdocumentatie — O"
    Deze pagina is lokaal ontwikkeld voor latere review in Acceptatie. Zij is nog
    niet definitief/as-built in Productie en autoriseert geen cleanup.

## Doel en bronautoriteit

De Windows-laptop en OneDrive vormen voorlopig de actuele documentbron. De NAS
was historisch met laptop en OneDrive verbonden, maar is al langere tijd
losgekoppeld. Bestaande NAS-bestanden zijn daarom historische bronnen en mogen
niet zonder reconciliatie terug naar de actieve collectie.

De eerste baseline wordt met Synology Cloud Sync download-only opgenomen in:

```text
/volume1/data/import/cloud/onedrive/current
```

Cloud Sync verwijdert geen doelbestanden wanneer een bestand uit OneDrive
verdwijnt. De importmap is geen actieve SMB-werkmap en blijft tijdens assessment
beschermd.

De eerste read-only meting op 1 augustus 2026 telde 3.682 fysieke bestanden en
10,41 GiB. Een full reconciliation vond 15.896 bestanden binnen alle
geconfigureerde scanroots en hoefde geen jobs in te plannen. Dit bevestigt dat
de baseline door CORE was verwerkt; het is geen cleanupbesluit.

## Read-only assessment

Voer na een voltooide Cloud Sync-run, een geslaagde scannerreconciliation en bij
voorkeur een beschermende snapshot uit:

```bash
core cleanup onedrive-baseline \
  --source /volume1/data/import/cloud/onedrive/current \
  --as-of 2026-08-01 \
  --active-years 2 \
  --baseline-at 2026-08-01T12:38:51+02:00 \
  --snapshot-ref onedrive-baseline-20260801-before-golden-record-assessment \
  --dry-run
```

`--snapshot-ref` registreert alleen de door de beheerder opgegeven referentie.
De tool maakt, controleert of verwijdert zelf geen snapshot. Laat de optie weg
wanneer nog geen snapshot bestaat.

De selectie van actuele bestanden staat los van duplicaatmatching. Bestanden
met een filesystem-mutatiedatum binnen twee jaar worden `active_candidate`;
oudere bestanden worden `legacy_review_candidate`. Ontbrekende, ongeldige of
toekomstige datums vereisen temporele review. Gebruik uitsluitend deze selectie
zonder historische vergelijking met:

```bash
core cleanup onedrive-baseline \
  --source /volume1/data/import/cloud/onedrive/current \
  --as-of 2026-08-01 \
  --active-years 2 \
  --skip-exact-matching \
  --dry-run
```

In deze eerste versie is `modified_at_fs` de beschikbare bronmutatiedatum. Die
heeft lage confidence: kopieer- of syncacties kunnen de tijd beinvloeden. De
CORE-velden `created_at` en `updated_at` zijn observatietijden van CORE en gelden
niet als bewijs dat de gebruiker een document heeft geopend of gewijzigd.

De optionele exacte assessment:

1. selecteert actieve CORE-records binnen de baseline;
2. gebruikt uitsluitend volledige `content_sha256` plus bestandsgrootte als
   bewijs voor exacte inhoudsgelijkheid;
3. zoekt dezelfde exacte inhoud onder alle andere actieve CORE-paden;
4. koppelt de bestaande `content_group_id` en golden-recordkeuze waar aanwezig;
5. maakt een volledig manifest, een compacte review en een samenvatting;
6. berekent conservatieve bovengrenzen voor mogelijke ruimtebesparing;
7. wijzigt geen bestand, database-record, Cloud Sync-instelling, snapshot of
   backup.

Vergelijkbare namen, datums, classificaties, MIME-types en gedeeltelijke hashes
zijn nooit bewijs voor exacte duplicaten.

## Uitkomsten

| Relatie | Voorstel | Betekenis |
|---|---|---|
| `baseline_only` | `retain_baseline` | Geen andere actieve exacte kopie bekend |
| `exact_duplicate_historical` | `review_historical_exact_duplicates` | Exacte kopie buiten de baseline |
| `exact_duplicate_within_baseline` | `review_onedrive_exact_duplicates` | Exacte kopieën binnen OneDrive-baseline |
| `exact_duplicate_all_zones` | `review_exact_duplicates_all_zones` | Meerdere baseline- en historische kopieën |
| `unassessed` | `blocked_missing_full_hash` | Geen volledige SHA-256; geen matching of cleanup |

Iedere manifest- en reviewrij bevat:

```text
baseline_protected=true
execution_authorized=false
```

Er bestaat bewust geen `--apply`-modus in deze delivery slice.

## Golden record en fysieke kopie

Een golden record is de duurzame logische identiteit voor één exacte
inhoudsgroep. De fysieke bestanden blijven afzonderlijke bronnen. Een bestaande
golden-recordkeuze wordt als canonical auditreferentie gerapporteerd, ook als de
gekozen fysieke bron historisch is. Dat maakt OneDrive niet minder actueel en
autoriseert geen verwijdering: bronautoriteit, versiehistorie en het toekomstige
SMB-knipmoment zijn afzonderlijke besluiten.

De ruimtecijfers zijn bovengrenzen:

- historische kopieën die inhoudelijk door de beschermde baseline zijn
  vertegenwoordigd;
- extra exacte kopieën binnen de baseline;
- theoretisch maximum wanneer één fysieke kopie per exacte inhoudsgroep blijft.

Voor fysieke cleanup blijven metadata, gevoeligheid, bewaartermijn, fallback,
hersteltest en expliciete menselijke goedkeuring verplicht.

Golden-recordselectie begint pas nadat volledige SHA-256 plus grootte de exacte
inhoudsgroep hebben bewezen. Binnen die groep gebruikt CORE de bestaande
deterministische voorwaarden: tijdelijke bestanden en copy-, backup- en
archiefpaden krijgen strafpunten; de scoremarge bepaalt de confidence; een
gelijke score blijft zichtbaar als `golden_selected_tiebreak`. Een bestaande
golden-keuze blijft behouden zolang die nog tot de actieve exacte inhoudsgroep
behoort.

Een recente filesystem-mutatiedatum kiest dus nooit zelfstandig een golden
record. `created_at` en `updated_at` leveren in het bestaande algoritme alleen
kleine punten voor aanwezige metadata op, niet voor recency.

## Review en fallback

De vervolgstroom is strikt:

```text
baseline → exact matching → dry-run → review → fallback/hersteltest
         → expliciete batchgoedkeuring → tijdelijke recoverysnapshot
         → gecontroleerde cleanup → snapshot na hersteltermijn laten vervallen
```

Fallbackniveaus:

1. exacte duplicaten: canonical inhoud plus catalogus- en besluitgeschiedenis;
2. oud maar relevant: versleuteld offline Hyper Backup-archief met hersteltest;
3. lage informatiewaarde: compacte evidence snapshot na review;
4. onzeker of gevoelig: retention-, conflict- of sensitive review.

Prullenbak, quarantainemap en lokale Btrfs-snapshot leveren aanvankelijk weinig
ruimte op. Volledige recovery én lokale ruimtebesparing vereist een externe of
offline kopie. Ruimte van verwijderde bestanden komt pas vrij nadat snapshots
die de datablocks vasthouden gecontroleerd zijn vervallen.

## Eventmodel en `candidate_file_id`

In `file_events` is `file_id` het onderwerp of resultaat van het event.
`candidate_file_id` verwijst naar het andere bestandrecord dat CORE tijdens een
identiteits- of selectiebeslissing heeft beoordeeld. Voorbeelden zijn een
rename-/move-kandidaat, een mogelijke identity match of de vorige golden-file
bij `GOLDEN_RECORD_CHANGED`.

`candidate_file_id` betekent op zichzelf niet dat een bestand een duplicaat of
delete candidate is. Lees het altijd samen met:

```text
event_type
decision
confidence_score
confidence_level
signals
reason
```

Een lege kandidaat is normaal wanneer geen tweede bestandrecord bij het event
betrokken was.

## Outputs

De genegeerde operationele exportmap ontvangt:

```text
onedrive-baseline-<timestamp>.md
onedrive-baseline-<timestamp>.csv
onedrive-activity-<timestamp>.csv
onedrive-duplicate-review-<timestamp>.csv
onedrive-baseline-latest.md
```

Het volledige manifest bevat paden voor lokale review en moet als gevoelig
operationeel artefact worden behandeld. De samenvatting bevat geen
documentinhoud.

## Veiligheidsgrenzen

- Geen assessment tijdens een nog veranderende baseline.
- Bij kritieke opslagdruk wordt Cloud Sync gepauzeerd; er wordt niet gehaast
  verwijderd.
- Een bestaand golden record is geen verwijderautorisatie.
- Een ruimtebesparingsgetal is geen verwijderautorisatie.
- Harde cleanup vereist een afzonderlijke implementatie, review en expliciete
  opdracht voor een exact afgebakende batch.
- De documentatie gaat later via review in A naar definitief/as-built in P.
