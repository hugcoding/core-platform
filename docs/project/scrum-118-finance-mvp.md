# CORE Finance MVP — SCRUM-118

De eerste verticale slice biedt een afzonderlijke CORE Finance-pagina, lokale CAMT-import, bronherleiding, handmatige categorieën en beoordeling van mogelijke dubbele transacties. Het fundamentontwerp blijft de roadmap; onderstaande scope beschrijft wat daadwerkelijk is geïmplementeerd.

## Scope en gebruik

Open `/corefinance` en ontgrendel met de persoonlijke toegangscode uit het lokale runtimebestand `finance/access-code.txt`. `XML importeren` zet een scanopdracht klaar voor de ingestworker. Accounts zijn gemaskeerd; bedragen, omschrijvingen en tegenpartijen worden uitsluitend aan de ontgrendelde browser geleverd. Via de kolomkoppen kunnen datum, tegenpartij, omschrijving, categorie en bedrag oplopend of aflopend worden gesorteerd. Dit geldt voor de volledige gefilterde selectie, met stabiele paginering. Bij datumsortering blijven boekingen binnen dezelfde dag in bronvolgorde: CORE-bronbestand-ID, numeriek statementnummer en numeriek XML-entrynummer. Deze volgorde blijft behouden bij zowel oplopende als aflopende datums; ze suggereert geen tijdstip of chronologie tussen verschillende bestanden. Tekstsortering ontsleutelt alleen lokaal in geheugen en maakt geen onversleutelde sorteerindex. De totalen zijn mutaties binnen de filters, geen banksaldo. Eigen overboekingen zijn inbegrepen.

Ondersteund: losse UTF-8 ASN CAMT `camt.053.001.02` XML-bestanden, geboekte EUR-mutaties, één eigenaar. Een `Ntry` is één transactie; onderliggende `TxDtls` zijn aanvullende broninformatie. Begin/eindsaldi worden gecontroleerd indien aanwezig. Andere versies, valuta, ZIP, CSV, PDF, MT940 en Open Banking volgen later. De UI heeft geen AI-laag.

## Lokale categorievoorstellen

Na het handmatig opslaan van een categorie zoekt Finance op jouw verzoek soortgelijke boekingen. Voor een eerder ingedeelde boeking: open de details en klik **Soortgelijke betalingen voorstellen**. De voorstellen gelden voor alle eigen rekeningen en perioden, uitsluitend voor boekingen zonder categorie. Vink gewenste voorstellen aan en klik **Selectie accorderen**. **Alle zichtbare voorstellen** selecteert alleen de getoonde lijst. Sluiten verandert niets. De selectie wordt in een database-transactie opnieuw gecontroleerd en opgeslagen: bij een verouderd voorstel wordt niets uit die aanvraag toegepast. Iedere betaling behoudt een eigen append-only audit-event. Maximaal 50 voorstellen worden tegelijk getoond; na bevestigen vult de lijst zich aan.

De eerste deterministische herkenners zijn de OVpay-marker in omschrijvingen en de combinatie van een concrete tegenpartij met dezelfde tegenrekening. Bedrag, datum en wisselende betalingsreferenties bepalen een OVpay-match niet; richting (afschrijving/bijschrijving) en valuta moeten wel gelijk zijn. Algemene betaalteksten, alleen MCC, paymentprocessors en samengestelde boekingen zijn onvoldoende bewijs. De categorie komt uitsluitend uit jouw handmatige oordeel, niet uit een vaste koppeling OVpay=Vervoer. Tegenstrijdige actuele handmatige voorbeelden blokkeren voorstellen. Eerder toegepaste voorstellen worden niet opnieuw als onafhankelijk leerbewijs gebruikt.

Dit is een lokale, door de gebruiker aangevraagde vergelijking, geen externe API, AI-model, permanente automatische regel of achtergrondworker. Nieuwe imports kun je opnieuw met hetzelfde voorbeeld vergelijken. Er wordt maximaal een selectie van 25.000 boekingen met dezelfde richting/valuta gescand; daarboven volgt een melding zonder wijzigingen. Voorstellen zijn tijdelijke zoekresultaten. Bevestiging maakt een append-only reviewevent met `source_review_id` en `suggestion_method`; bron, actuele categorie, conflictsituatie en idempotency worden opnieuw gecontroleerd. Bestaande categorie?n worden nooit via deze route overschreven.

Voor installatie is eenmalig `database/migrations/20260917_add_finance_suggestion_audit.sql` nodig, v??r activeren van de nieuwe dashboardcode. De down-migratie onder `rollback/` weigert auditbewijs van reeds bevestigde voorstellen te verwijderen. Bij rollback van code blijft dat bewijs behouden. Er is geen herimport nodig en er worden geen gegevens naar buiten gestuurd.

## Periode kiezen

Het menu **Periode** biedt alle perioden, beschikbare jaren, maanden en **Aangepast datumbereik**. Kies bij datumbereik **Van** en **Tot en met**, en klik **Toepassen**. Beide grensdatums zijn inclusief; de boekdatum bepaalt de selectie. De selectie geldt voor transacties, totalen, categorie- en rekeningfilters, sortering en alle pagina's. Wisselen van periode begint op pagina 1. Tijdens het invoeren blijft de vorige selectie actief tot Toepassen is gekozen.

Voor deze uitbreiding is geen database-migratie of herimport nodig; alleen het dashboard moet na merge/pull opnieuw worden gebouwd en gestart. De bestaande Finance- en rekeningnamen-migraties blijven vereist.

## Eigen rekeningnamen

Selecteer een rekening en kies **Naam wijzigen**. De weergavenaam verschijnt met de laatste vier IBAN-cijfers in de rekeningkeuze. **Standaardnaam herstellen** voegt een nieuw event toe; bestaande historie en bankidentiteit blijven intact. Herimport verandert de gekozen naam niet. Namen zijn versleuteld opgeslagen in `finance.finance_account_name_events`; gelijktijdige wijzigingen worden op hun voorganger gecontroleerd.

Na merge/pull eerst de aanvullende migratie uitvoeren, daarna het dashboard opnieuw bouwen/starten met de bestaande deploymentconfiguratie:

```sh
/usr/local/bin/docker exec -i postgres psql -X -v ON_ERROR_STOP=1 -U hugo -d nasdb_test < database/migrations/20260916_add_finance_account_names.sql
```

Deze migratie is eenmalig en vereist het bestaande Finance-schema. De gelijknamige down-migratie onder `rollback/` werkt alleen zolang geen naamwijzigingen zijn opgeslagen. Bij code-rollback met bestaande naamreviews blijft de tabel behouden. Deze wijziging voert zelf geen migraties uit bij opstarten.

## Bron en idempotency

Originele bestanden worden uitsluitend gelezen. De bestaande `public.files`-ID wordt hergebruikt of aangemaakt, met afzonderlijke bronvoorkomens voor kopieën. Er is geen tweede algemene documentenregistratie. De Finance-bron bewaart bovendien een versleutelde exacte kopie zodat bronherleiding niet afhankelijk is van een later gewijzigde NAS-file.

Bestandsidentiteit is SHA-256 plus lengte; een import is uniek op bron en parserversie. Herhaling publiceert geen nieuwe transacties. Transacties verwijzen via importrecords naar batch, bron, statement en XML-entry. Een keyed fingerprint over rekening, datums, bedrag, valuta, omschrijving en tegenrekening signaleert overlap tussen imports. Deze fingerprint is bewust niet uniek: twee gelijke betalingen binnen dezelfde bron blijven twee transacties. Mogelijke overlap tussen verschillende bronnen vereist expliciete beoordeling als dezelfde of afzonderlijke betaling. Er wordt nog geen universeel betrouwbare banktransactie-ID verondersteld.

Imports doorlopen append-only events: ontvangen, gevalideerd, geïmporteerd, gedeeltelijk, afgewezen of teruggedraaid. Parserfouten wijzen de volledige bron af; gedeeltelijk betekent dat niet-ambigue records gepubliceerd zijn en overlap wacht op review. Rollback voegt een event toe en sluit de bijdrage van de batch uit; transacties met een andere actieve bron blijven zichtbaar. Herimport activeert een teruggedraaide batch niet stilzwijgend opnieuw.

## Privacy en bestaande CORE-aansluitpunten

De Finance-root wordt uitgesloten van generieke tekstextractie, OCR, LLM-prompts en automatische Workset-AI. De bestaande privacyclassificatie kent deze root hoog risico toe. Generieke downloads en migratieacties mogen de root niet gebruiken. De Finance-worker publiceert uitsluitend technische reason codes, queue-aantallen en heartbeats in CORE Pulse. Gecontroleerde uitvoering heeft voorrang via een gedeeld admission lock. CPU, vrij geheugen, CORE-achterstand en PostgreSQL-activiteit bepalen of verwerking wacht; drie gezonde metingen zijn nodig voor aanvang.

IBAN, tegenpartijen, omschrijvingen en oorspronkelijke XML zijn applicatieversleuteld met een lokale sleutel buiten Git. Boekingsdatums, bedragen en relaties staan als operationele gegevens in PostgreSQL; dit is geen volledige databaseversleuteling. NOLOGIN-rollen beperken de runtimebevoegdheden; immutable triggers voorkomen wijzigen, wissen en truncate van Finance-historie. Database- en NAS-beheerders blijven onderdeel van de vertrouwde omgeving. De eigenaarstoegang gebruikt een tijdelijke HttpOnly/SameSite-cookie, expliciete Origin-controle, rate limiting en no-store-responses. Gebruik voor toegang buiten het vertrouwde LAN HTTPS; dit MVP voegt geen algemene CORE-identiteitsprovider toe.

De sleutelmap moet afzonderlijk beveiligd worden geback-upt samen met de database. Verlies van de datasleutel maakt de beschermde inhoud onleesbaar. Sleutelrotatie, multi-user autorisatie en automatische retentie zijn vervolgwerk. Gebruik de Finance-root niet als opslag voor reeds elders door AI verwerkte kopieën: deze afscherming wist geen historische externe verwerking.

## Schema en audit

Forward: `database/migrations/20260916_add_finance_mvp.sql`. Down: het gelijknamige bestand onder `rollback/`. De down-migratie werkt uitsluitend op een lege Finance-installatie en weigert financiële historie te verwijderen. Bij gevulde data is de operationele rollback: worker stoppen en Finance uitschakelen, met behoud van schema, bronnen en sleutels.

Accounts, bronnen, bronvoorkomens, batches, records, transacties en bronlinks zijn afzonderlijke relaties. Deferrable constraints eisen een passende rekening en bronlink voor elke transactie. Categorie-reviews vormen een keten met optimistic concurrency en idempotency. Tegenpartijen hebben een gereserveerde tabel; centrale tegenpartijresolutie volgt later. Correctie van een categorie is een nieuw reviewevent. Het herzien van een definitieve duplicate-beslissing heeft nog geen aparte UI-workflow.

## Installatie en validatie

De acceptance-deployment gebruikt een geïsoleerde builddirectory en `tools/runtime/finance-compose.override.yml`, met de oorspronkelijke Compose-projectnaam, `.env` en projectdirectory. De bestaande NAS-checkout en gebruikersbestanden blijven intact. `tools/runtime/finance_bootstrap.py` maakt lokale sleutels en toegangscode aan zonder ze af te drukken. Finance staat standaard uit; het Compose-profiel `finance` activeert de worker. Het brondirectory en de sleutelmap zijn read-only gemount voor de worker.

Tests gebruiken uitsluitend fictieve data. De aparte PostgreSQL-teststack gebruikt database `core_finance_test`, tmpfs en geen bankmounts. De suite controleert onder meer concurrency, bestand-idempotency, gelijke afzonderlijke betalingen, ambiguity-review, append-only categorieën, bronlinks, afgeschermde downloads, rollback en voorrang van gecontroleerde uitvoering. De UI-preview gebruikt uitsluitend synthetische responses. Werkelijke imports mogen alleen lokaal plaatsvinden; uitlezen voor oplevercontrole blijft beperkt tot statussen en aantallen.
