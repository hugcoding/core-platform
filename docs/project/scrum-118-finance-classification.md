# CORE Finance: type, categorie en classificatie

## MVP en grenzen

Een banktransactie blijft onveranderlijk in `finance_transactions`, inclusief de versleutelde oorspronkelijke omschrijving. Classificatie is een nieuwe stap in `finance_review_events`. De actuele classificatie staat in `v_transactions`; het detailvenster toont maximaal de laatste 100 events. Er is geen herimport nodig.

De UI biedt transactietype, hoofdcategorie, subcategorie en genormaliseerde merchant. **Oordeel opslaan** maakt uitsluitend een handmatig oordeel; voorstellen openen alleen via de aparte knop. Een categorie heeft een aanbevolen type, dat je expliciet kunt overnemen of vervangen. De categorienaam bepaalt nooit de boekhoudkundige betekenis.

Categoriebeheer via de UI, AI, automatische toepassing op nieuwe imports en automatische transfermatching zijn vervolgstappen. De huidige herhaalregels gebruiken handmatige voorbeelden en leveren voorstellen op; toepassing vereist accorderen. Er is geen nieuwe worker/queue, dus geen extra Pulse-service. De bestaande importworker en belastingbewaking veranderen niet.

## Schema en compatibiliteit

- `finance_transaction_types`: negen codes, namen en afzonderlijke indicatoren voor inkomen/uitgaven.
- `finance_categories`: bestaande stabiele `code` blijft behouden; toegevoegd worden UUID `id`, `name`, `parent_id`, aanbevolen `transaction_type`, `active`, `sort_order`, `is_system`, `created_at`, `updated_at`. `label` is een gegenereerde compatibiliteitskolom. Bestaande namen worden behouden. De seed bevat 18 hoofdcategorieen en alle gevraagde subcategorieen. Dubbele namen zoals Onderhoud hebben verschillende codes.
- Twee niveaus in deze MVP. Alleen een hoofdcategorie kan ouder zijn; cycli en een derde niveau worden geweigerd. Naam, volgorde, status en ouder kunnen later worden aangepast zonder codes te wijzigen. Verwijderen en wijzigen van ID/code zijn geblokkeerd.
- `finance_category_events`: append-only voor/na-snapshots van configuratiewijzigingen, actor en tijd. Beheer gebeurt voorlopig via gecontroleerde databasewijzigingen; de applicatierol krijgt geen onbeperkte categorie-mutaties. De seed is onderdeel van de forward migration.
- `finance_review_events`: type, hoofd-/subcategoriecode, `merchant_id`, `classification_source` (MANUAL/MERCHANT/RULE/AI), nullable confidence tussen 0 en 1, bevestigingsstatus, bestaande eventdatum, bronreview, regelversie en optionele modelversie. Bestaande events worden niet bijgewerkt. Een historisch oordeel zonder type wordt `UNKNOWN`; een ontbrekend oud type is geen tegenstrijdig nieuw leerbewijs.
- `finance_counterparties` wordt hergebruikt voor merchants: UUID, domeingescheiden HMAC van de genormaliseerde naam en versleutelde naam. Geen tweede tegenpartijenregister. De eerste spelling van dezelfde genormaliseerde merchant blijft de weergavenaam; geen globale merchant-rename in deze MVP.
- Reservering op reviewevents: `transfer_id`, `linked_transaction_id`, `transfer_status` (UNMATCHED/PROPOSED/CONFIRMED/REJECTED). Een link naar zichzelf is verboden. Deze velden worden nog niet automatisch gevuld.

Historische categorie/subcategoriecodes blijven intact bij hernoemen of verplaatsen. Voor een nieuw oordeel moet de subcategorie op dat moment onder de gekozen actieve hoofdcategorie vallen. De configuratiehistorie verklaart vroegere ouderrelaties. Deactivatie verwijdert geen oude classificatie.

## Bron, herkenning, afleiding en bevestiging

1. Bank: oorspronkelijke bytes, bronregel en genormaliseerde boeking blijven intact.
2. Herkenning: conservatieve lokale herkenners identificeren OVpay, specifieke Shell-/AH-markers of een exacte tegenpartij-plus-tegenrekening. Alleen een algemene betaalprocessor/MCC is onvoldoende.
3. Afleiding: een nog actueel handmatig voorbeeld levert type, hoofd-/subcategorie en merchant. Tegenstrijdige expliciete handmatige voorbeelden blokkeren voorstellen. Er is geen ingebouwde koppeling van een merk naar een categorie.
4. Bevestiging: accorderen schrijft een afzonderlijk MERCHANT-reviewevent met de volledige classificatie, bronreview en `local-merchant-v2`. Het bronreview-ID is de identiteit/versie van de voorbeeldregel. Er is geen extra regelengine. Eerder toegepaste voorstellen worden niet als onafhankelijk leerbewijs hergebruikt.

Handmatige merchantinvoer normaliseert Unicode en witruimte, niet willekeurig bedrijfsnamen. Beperkte herkenners bieden bijv. `SHELL STATION 1234` -> `Shell` of `AH 1234` -> `Albert Heijn` aan. Dat vult alleen het invoerveld als voorstel; pas opslaan bevestigt het. Richting en valuta blijven deel van de match. Bedrag, locatie en terminalnummer zijn geen categorie-identiteit. Samengestelde bankentries worden niet als een merchant behandeld.

Confidence is nullable: de huidige herkenners zijn niet gekalibreerd en krijgen geen verzonnen percentage. Handmatige bevestiging heeft een eigen boolean en bron, geen pseudo-confidence van 100%. Toekomstige classifier-events kunnen bron, confidence en modelversie bevatten, maar onbevestigde events verschijnen niet als actuele classificatie. Bevestigde automatische events mogen bestaande bevestigde oordelen niet vervangen. Een handmatige correctie blijft mogelijk, ook na een onbevestigd classifier-event, met een complete fysieke eventketen.

## Totalen

De oorspronkelijke **Bijgeschreven**, **Afgeschreven** en **Netto mutatie** blijven bankmutaties inclusief interne transfers. Daarnaast:

- Geclassificeerd inkomen: getekende som van type INCOME.
- Geclassificeerde uitgaven: negatieve getekende som van EXPENSE en TAX. Een positieve terugbetaling met hetzelfde uitgavetype verlaagt die uitgaven.
- Interne transfers uitgaand: afzonderlijke som van negatieve TRANSFER-mutaties; geen uitgaven.
- Type nog onbekend: aantal UNKNOWN-mutaties, niet stilzwijgend als uitgave beschouwd.

SAVING, INVESTMENT, DEBT, CORRECTION en TRANSFER zitten niet in geclassificeerde uitgaven. TAX wel. Gemengde betalingen zoals rente plus aflossing kunnen nog niet worden gesplitst; kies bewust het passende type en beschouw dit niet als volledige boekhouding. Geen transfer matching of saldoberekening wordt gesuggereerd.

## API

`POST /api/v1/finance/transactions/{id}/classification`:

```json
{"transaction_type":"EXPENSE","category":"vervoer","subcategory":"vervoer_brandstof","merchant":"Shell","previous":null,"key":"een-unieke-uuid"}
```

`previous` is het actuele `review_id`; `key` blijft gelijk bij retry van dezelfde inhoud. Gewijzigde inhoud met dezelfde sleutel geeft 409. Bron/confidence/bevestiging zijn servergestuurd voor deze handmatige route. `GET .../{id}/classifications` toont de historie. `/data` ondersteunt `transaction_type` en `subcategory` naast bestaande filters. De bestaande categorie-only API blijft bestaan en behoudt type en merchant; een subcategorie wordt bij deze legacy-route gewist.

Selectie-accordering is atomair en controleert alle classificatievelden, voorbeeldstatus en taxonomie opnieuw. Een bewust handmatig UNKNOWN-oordeel wordt niet via voorstellen overschreven. Bestaande sessie-, same-origin-, no-store- en privacygrenzen gelden voor alle nieuwe routes. Merchantnamen komen niet in logs of onversleutelde indices. De bankdata verlaat de NAS niet.

## Migratie, rollback en test

Forward: `database/migrations/20260918_add_finance_classification.sql`, na de drie eerdere Finance-migraties. Niet herhaald uitvoeren. De migratie voegt alleen verrijkingsstructuur toe; geen transacties of reviewevents worden herschreven. Het oorspronkelijke categorieoverzicht wordt voor veilige rollback bewaard.

De down-migratie onder `rollback/` herstelt het vorige schema alleen zolang er geen nieuwe classificatiegegevens of categoriebeheerhistorie zijn. Bij zulke historie weigert zij expliciet; behoud dan het schema en rol uitsluitend dashboardcode terug. Dit voorkomt vernietiging van gebruikersoordelen. De vorige dashboardcode kan nog categorieen lezen via de `label`-compatibiliteitskolom.

Tests gebruiken uitsluitend synthetische gegevens in een afzonderlijke PostgreSQL-container: forward/down/forward, taxonomieconstraints, bronimmutabiliteit, versleutelde merchants, volledige voorstelclassificatie, optimistic concurrency/idempotency, auth/origin, handmatige voorrang, transfer-totalen, onbekende typen en geweigerde destructieve rollback. De UI is met de synthetische preview getest.
