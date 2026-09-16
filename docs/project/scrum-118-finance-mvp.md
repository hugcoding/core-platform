# CORE Finance MVP — SCRUM-118

De eerste verticale slice biedt een afzonderlijke CORE Finance-pagina, lokale CAMT-import, bronherleiding, handmatige categorieën en beoordeling van mogelijke dubbele transacties. Het fundamentontwerp blijft de roadmap; onderstaande scope beschrijft wat daadwerkelijk is geïmplementeerd.

## Scope en gebruik

Open `/corefinance` en ontgrendel met de persoonlijke toegangscode uit het lokale runtimebestand `finance/access-code.txt`. `XML importeren` zet een scanopdracht klaar voor de ingestworker. Accounts zijn gemaskeerd; bedragen, omschrijvingen en tegenpartijen worden uitsluitend aan de ontgrendelde browser geleverd. Via de kolomkoppen kunnen datum, tegenpartij, omschrijving, categorie en bedrag oplopend of aflopend worden gesorteerd. Dit geldt voor de volledige gefilterde selectie, met stabiele paginering. Tekstsortering ontsleutelt alleen lokaal in geheugen en maakt geen onversleutelde sorteerindex. De totalen zijn mutaties binnen de filters, geen banksaldo. Eigen overboekingen zijn inbegrepen.

Ondersteund: losse UTF-8 ASN CAMT `camt.053.001.02` XML-bestanden, geboekte EUR-mutaties, één eigenaar. Een `Ntry` is één transactie; onderliggende `TxDtls` zijn aanvullende broninformatie. Begin/eindsaldi worden gecontroleerd indien aanwezig. Andere versies, valuta, ZIP, CSV, PDF, MT940 en Open Banking volgen later. De UI heeft geen AI-laag.

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
