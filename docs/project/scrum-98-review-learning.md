# SCRUM-98 gecontroleerd leren uit portalbeoordelingen

## Contextbewuste traject- en werkgevermappen

Voor sollicitatiedocumenten kan CORE een werkgever- of trajectmap voorstellen op
basis van eerder geaccepteerde menselijke doelpaden. `Sollicitaties` is daarbij
de leidende canonieke laag. Tijdelijke bronmappen zoals `uitzoeken`, `nieuw`,
`tijdelijk`, `algemeen` en `ongesorteerd` worden niet overgenomen. Ook generieke
familielagen zoals `CV` en `Motivatiebrieven` worden niet als werkgever geleerd.

Een kandidaatregel ontstaat pas na minimaal drie consistente menselijke
voorbeelden en wordt geblokkeerd door een relevant tegenvoorbeeld. De herkenning
gebruikt context uit bestandsnaam en bronpad, maar alleen binnen een herkenbare
sollicitatiecontext. In het portaal blijven support, agreement en de bronreviews
zichtbaar als lineage. De regel maakt uitsluitend een voorstel: er wordt geen
bestand verplaatst en geen regel automatisch geactiveerd.

## Veilige bestandsnaamvoorstellen

In dezelfde portalbeoordeling kan een andere bestandsnaam worden voorgesteld.
CORE behoudt altijd de bestaande extensie, normaliseert tekens die niet veilig
zijn op de opslag en toont direct het volledige nieuwe doelpad. Voor opslag van
het oordeel controleert CORE read-only of dat pad al bij een actief bestand of
een ander geaccepteerd voorstel hoort.

De oorspronkelijke naam, ruwe invoer, genormaliseerde naam, normalisatieredenen
en eventuele conflicten worden append-only als menselijke learning evidence
opgeslagen. Dit is uitsluitend een voorstel: CORE hernoemt, verplaatst of
overschrijft hierbij geen bestand.

## Origineel document openen

Het oorspronkelijke pad wordt als standaard Windows/SMB-pad getoond, bijvoorbeeld
`\\192.168.68.105\data\...`, en is een klikbare documentlink. CORE leest
het bestand via de read-only NAS-koppeling en biedt het met `no-store` aan de
browser aan; PDF opent doorgaans direct en een Office-bestand wordt aan de
browser of gekoppelde app overgedragen. Alleen bestaande databasebestanden onder
`/volume1/data` zijn toegestaan. Naast de link staat uitsluitend een compact
icoon om het SMB-pad te kopiëren.

Microsoft Office-documenten gebruiken op Windows het geregistreerde Word-,
Excel- of PowerPoint-protocol, zodat de desktopapp wordt geopend. PDF en veilige
browserformaten openen inline. Als een Office-protocol niet beschikbaar is,
levert de read-only CORE-route het bestand als download en nooit als ruwe
binaire webpagina.

CORE normaliseert menselijke doelpadvoorstellen vóór opslag. Meerdere `/`
worden één separator; relatieve segmenten, control characters en paden buiten
de beheerde roots worden geweigerd. De ruwe invoer blijft naast het
genormaliseerde pad auditbaar.

`Algemeen` blijft een technische fallback maar veroorzaakt geen betekenisloze
fysieke maplaag. Generieke trajecten en families worden met auditbare
reason-codes uit het voorgestelde pad weggelaten.

## Read-only learninganalyse

```bash
core workset review-learning-analyze --minimum-support 3 --dry-run
```

De analyse groepeert uitsluitend herhaalde, geaccepteerde menselijke
correcties. Kandidaten bevatten support, confidence, conflicten, voorbeelden,
reason-codes en status `candidate_only`. Er worden geen regels geactiveerd,
modellen aangepast, databasewaarden geschreven of bestanden verplaatst.

De JSON-export bevat een begrensde `llm_learning_context`. Een toekomstige
portalvraag aan een LLM gebruikt deze context als advies met expliciete
menselijke provenance. Kandidaatpatronen zijn geen actieve businessregels en
geven de LLM nooit bevoegdheid regels te activeren of bestanden te wijzigen.

## Privacy-learning uit SCRUM-99

Dezelfde opdracht analyseert ook privacyoordelen. Alleen het laatste
append-only privacyoordeel per document telt mee, zodat herhaald corrigeren van
één document de support niet kunstmatig verhoogt. Privacykandidaten bevatten:

- het verklaarbare bronsignaal en oorspronkelijke CORE-voorstel;
- het dominante menselijke oordeel;
- support en agreement-percentage;
- maximaal vijf expliciete tegenvoorbeelden;
- confidence en status `candidate_only`.

Bij minder dan 75% agreement blijft een patroon uitsluitend zichtbaar als
analyse en is het niet geschikt voor activatiereview. Ook bij hoge agreement
wordt niets automatisch geactiveerd. Een kandidaat mag privacy `Hoog` nooit
automatisch verlagen. De analyse schrijft JSON, een algemeen CSV-bestand, een
afzonderlijk privacy-CSV-bestand en Markdown; database, bestanden, regels en
modellen blijven ongewijzigd.

## Controle van CORE-voorstellen

De analyse meet daarnaast afzonderlijk de kwaliteit van categorie-, familie- en
doelpadvoorstellen. Per onderdeel toont het rapport hoeveel laatste menselijke
oordelen:

- het voorstel ongewijzigd bevestigden;
- een gecorrigeerde waarde bevatten;
- het voorstel afwezen;
- werden uitgesteld of overgeslagen.

Agreement wordt berekend over werkelijk beoordeelde voorstellen. Maximaal vijf
tegenvoorbeelden tonen document, CORE-voorstel en menselijke correctie. De
vaste export `review-learning-proposal-quality-latest.csv` maakt deze controle
ook zonder het brede JSON-rapport toegankelijk. Dit is kwaliteitsmeting en
activeert geen categorie-, familie- of doelpadregel.

## Systematiek en passendheid van doelpaden

CORE controleert zowel het oorspronkelijke systeemvoorstel als een handmatig
voorgesteld pad. Menselijke invoer is waardevol bewijs, maar wordt niet
automatisch als waarheid beschouwd. De audit controleert minimaal:

- beheerde absolute root en veilige padnormalisatie;
- behoud van de bestandsnaam;
- aanwezigheid van betekenisloze `Algemeen`-lagen;
- aansluiting van de categorie op de fysieke categorielaag;
- conflicterende familielagen;
- bewuste weglating van een familielaag als niet-blokkerende observatie.

Uitkomsten zijn `pass`, `needs_review` of `invalid`, met reason-codes per pad.
`review-learning-path-audit-latest.csv` bevat zowel CORE- als menselijke
voorstellen. De audit wijzigt geen opgeslagen voorstel en verplaatst niets.

## Gecontroleerde doelpadassistent

De portal accepteert zowel een doelmap als een volledig doelpad. Bij een
doelmap voegt CORE uitsluitend voor normalisatie en analyse de bestaande
bestandsnaam toe. Daardoor is `/Geldzaken/Belasting` een geldige doelmap en
wordt dit niet meer ten onrechte als een gewijzigde bestandsnaam aangemerkt.

Technische verschillen zoals dubbele `/` worden veilig genormaliseerd.
Inhoudelijke verschillen worden nooit stil aangepast. De assistent vergelijkt
invoer met canonieke en eerder door een mens bevestigde paden. Bij een kleine
afwijking, bijvoorbeeld `Belastingen` tegenover `Belasting`, toont de portal
een expliciete **Bedoel je?**-suggestie. De reviewer kiest vervolgens:

- het bekende pad gebruiken;
- bewust een nieuw pad voorstellen;
- de invoer zelf aanpassen.

De oorspronkelijke invoer, de genormaliseerde waarde, het type invoer
(`directory` of `full_path`), de aangeboden suggestie en de menselijke keuze
worden append-only vastgelegd. Dit is learning evidence; het activeert geen
regel, past geen model aan en wijzigt of verplaatst geen bestand.

Bij een wijziging van categorie of familie berekent de portal bovendien direct
een nieuw CORE-doelpad als read-only preview. De preview wordt pas onderdeel
van het append-only oordeel wanneer de reviewer de classificatie opslaat. Is
er al een handmatig doelpad ingevuld, dan blijft dat zichtbaar en leidend; de
live preview overschrijft menselijke invoer nooit.

## Bulkgoedkeuring van zichtbare voorstellen

De portal kan maximaal vijftig momenteel zichtbare voorstellen selecteren. De
keuze **Selecteer alle zichtbare voorstellen** selecteert nooit documenten op
een andere pagina of achter een ander filter. Vóór opslag vraagt CORE een
expliciete tweede bevestiging met alleen:

- bestandsnaam;
- het opnieuw door de server berekende of handmatig voorgestelde doelpad;
- het privacylabel dat als menselijk oordeel wordt bevestigd.

Een bulkbesluit schrijft één `document_review_batches`-record met een immutable
selectiesnapshot. Per document schrijft CORE daarnaast twee afzonderlijk
herleidbare append-only events: één voor classificatie/doelpad en één voor
privacy. Alle events verwijzen naar hetzelfde `batch_id`. Een UUID-gebaseerde
idempotency key en deterministische eventkeys voorkomen dubbele opslag bij een
herhaalde klik.

De server controleert categorie, familie, privacylabel, actuele werksetstatus
en doelpad opnieuw. Een ongeldig of inmiddels verouderd voorstel blokkeert de
hele batch; er ontstaat geen gedeeltelijk akkoord. Bulkgoedkeuring activeert
geen regels of modellen en verplaatst geen bestanden.

Voor sollicitatiedocumenten is het herkenbare traject de fysieke mapstructuur.
De familie blijft daar metadata en veroorzaakt geen extra submap voor `CV`,
`Motivatiebrieven`, `Vacatures` of `Gespreksvoorbereiding`. Alleen zonder een
betrouwbaar traject mag de familie als verzamelmap worden gebruikt. De
Nederlandse familienaam is **CV**; de technische code blijft `resumes`.

Database-uitbreiding voor acceptatie:

```bash
docker exec -i postgres psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test \
  < database/migrations/20260814_add_bulk_document_reviews.sql
```

## Overeenkomstige documenten en uitvoeringen

CORE hergebruikt een geaccepteerd menselijk oordeel nu als **voorstel** wanneer
een ander document conservatief als dezelfde logische documentidentiteit wordt
herkend. De eerste versie gebruikt een genormaliseerde bestandsnaam en ondersteunt
PDF-, DOCX- en XLSX-uitvoeringen. Daardoor kunnen bijvoorbeeld
`Motivatiebrief DUO.docx` en `Motivatiebrief DUO.pdf` bij hetzelfde logische
document horen, terwijl beide bestanden behouden blijven.

De veiligheidsgrenzen zijn:

- alleen een eerder geaccepteerd menselijk categorie- en familieoordeel telt;
- bekende taal- en kopiesuffixen mogen bij de naamvergelijking worden genegeerd;
- bij tegenstrijdige menselijke oordelen neemt CORE niets over;
- het doelpad wordt altijd opnieuw voor het afzonderlijke bestand opgebouwd;
- privacy wordt niet overgenomen en blijft een aparte bevestiging;
- het portaal toont de overeenkomstige documenten en de herkomst van het voorstel;
- een nieuw akkoord legt bronreviews en gerelateerde bestanden append-only vast
  in `document_review_events.proposal_evidence`;
- er wordt geen regel geactiveerd, geen model getraind en geen bestand gewijzigd.

Migratie voor de auditbare herkomst:

```bash
docker exec -i postgres psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test \
  < database/migrations/20260814_add_similar_document_review_evidence.sql
```

Terugdraaien kan met het gelijknamige script onder `database/migrations/rollback`.

## Lokale AI op een expliciete selectie

SCRUM-101 voegt in de werkset de knop **AI-voorstellen maken** toe. De gebruiker
selecteert expliciet één tot maximaal vijf zichtbare documenten binnen de huidige
filters. CORE leest lokaal een begrensde hoeveelheid tekst, kiest maximaal drie
relevante eerder bevestigde beoordelingen als voorbeelden en vraagt de lokale LLM
om een categorie, familie, lifecycle, documentrelatie en privacyadvies.

Het resultaat is herkenbaar **AI-advies** en verschijnt in dezelfde bestaande
reviewinterface. De gebruiker kan het ongewijzigd accepteren of corrigeren. Het
menselijke reviewevent verwijst naar het AI-voorstel, waardoor CORE het verschil
tussen advies en definitief oordeel later kan analyseren. Privacy blijft apart te
bevestigen.

Veiligheidsgrenzen:

- lokale, OpenAI-compatible provider via een privé-adres;
- maximaal vijf expliciet geselecteerde documenten;
- alleen actuele actieve bestanden;
- canonieke categorie- en familiecodes worden server-side gevalideerd;
- bij onvoldoende of ongeldige uitvoer onthoudt de LLM zich;
- ruwe documenttekst wordt niet in de AI-tabellen opgeslagen;
- runs zijn idempotent en leggen filters, model, prompt en bronreviews vast;
- geen regelactivering, modeltraining of bestandsmutatie.

Configuratie voor acceptatie staat in `.env`:

```dotenv
CORE_LLM_ENABLED=true
CORE_LLM_ENDPOINT=http://192.168.68.107:11434/v1
CORE_LLM_MODEL=qwen3.6:latest
CORE_LLM_TIMEOUT_SECONDS=600
```

Database-uitbreiding:

```bash
docker exec -i postgres psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test \
  < database/migrations/20260814_add_workset_llm_assistant.sql
```

### Contextafhankelijke sortering

De portaalstand **Slimme standaard** sluit aan op de actuele handeling:

- nog te beoordelen documenten staan op nieuwste relevante documentactiviteit;
- beoordeelde documenten en afzonderlijke besluitfilters staan op nieuwste
  menselijke beoordeling;
- bestandsnaam en `file_id` zijn vaste tie-breakers voor stabiele paginering.

De gebruiker kan dit overschrijven met **Recent actief**, **Laatst beoordeeld**,
**Bestandsnaam A–Z** of **Bestandsnaam Z–A**. Alleen vooraf toegestane
sorteercodes worden door de API omgezet naar SQL; vrije SQL-invoer is niet
mogelijk.

### Compacte AI-lineage en Nederlandse uitleg

Een geanalyseerd document krijgt een compact **AI**-icoon. De details openen met
hover of toetsenbordfocus op desktop en met een tik op mobiel. De popover toont
status, categorie, familie, confidence, reden, privacyadvies, documentrelatie,
model, promptversie en analysedatum. Het icoon is uitsluitend informatief en
bevestigt geen voorstel.

Prompt v2 verplicht een korte Nederlandse `reason`. Een duidelijk Engelstalige
reden wordt server-side afgewezen als `reason_not_dutch` en resulteert in een
onthouding met menselijke review. Historische Engelstalige redenen blijven voor
lineage in de database staan, maar krijgen in het portaal een Nederlandse
melding. Technische codes, modellen en promptversies blijven ongewijzigd
zichtbaar.
## Geleerde kandidaatfamilies

Een vrije familie zoals `Hypotheek` wordt niet direct onderdeel van de vaste
taxonomie. Wanneer minimaal drie actuele, geaccepteerde beoordelingen dezelfde
familie binnen dezelfde categorie voorstellen en er geen relevant
tegenvoorbeeld is, toont het portaal haar als kandidaatfamilie. Support en
bronbeoordelingen blijven zichtbaar. Met **Gebruik Hypotheek** wordt de waarde
opnieuw als expliciet menselijk familievoorstel ingevuld. De kandidaat wordt
niet automatisch canoniek en activeert geen regel.

## Eenmalige herkenning van een sollicitatietraject

Voor een duidelijk traject of werkgever hoeft CORE niet altijd drie dezelfde
correcties af te wachten. Eén geaccepteerd menselijk doelpad, bijvoorbeeld
`Sollicitaties/Rijnland`, mag meteen een voorstel met **medium confidence**
opleveren wanneer `Rijnland` letterlijk als afzonderlijke term in de
bestandsnaam of het bronpad van zowel het leervoorbeeld als het nieuwe document
staat. Bij drie consistente beoordelingen wordt de confidence **high**.

Een relevant tegenvoorbeeld blokkeert het voorstel. Tijdelijke bronmappen zoals
`uitzoeken`, `nieuw` en `algemeen` tellen niet als betekenisvolle doelmap. De
uitkomst blijft uitsluitend een verklaarbaar voorstel met verwijzing naar de
menselijke bronbeoordeling; CORE activeert geen regel en verplaatst geen bestand.
