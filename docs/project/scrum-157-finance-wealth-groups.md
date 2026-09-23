# SCRUM-157: vermogensgroepen en rekeningrelaties

## Gebruik

Open **Rekeningen beheren** in Finance. Maak een zelfgekozen groep aan, bijvoorbeeld een privégroep, een gezamenlijke groep of een afzonderlijke groep per kind. Kies daarna per rekening een weergavenaam, groep en relatie: **Van mij**, **Gezamenlijk** of **Alleen in beheer**. **Rekening opslaan** legt deze velden samen vast. De bestaande knop **Naam wijzigen** blijft bruikbaar.

Bestaande en nieuwe rekeningen beginnen als **Nog indelen**. De applicatie leidt eigendom nooit af uit het feit dat een bankbestand beschikbaar is. Een groep kiezen vereist ook een relatie; zonder groep blijft de relatie Nog indelen. Een rekening kan teruggezet worden op Nog indelen. Groepsnamen zijn vrij, niet hardcoded; namen en rekeninglabels zijn versleuteld met de bestaande Finance-sleutel.

De groepsfilter boven het overzicht bevat **Alle groepen (beheerd overzicht)**, **Nog indelen** en de aangemaakte groepen. Rekeningkeuze, perioden, transactielijst, paginering en bank-/classificatietotalen volgen de gekozen groep. De bestaande periode-, categorie-, subcategorie- en typefilters blijven werken. Een groepswissel wist de oude rekeningfilter. Als een rekening tijdens gebruik buiten de groep wordt geplaatst, wist de UI die rekeningfilter en laadt de groep opnieuw.

**Alle groepen is geen overzicht van uitsluitend eigen vermogen.** Er worden geen saldi, eigendomspercentages of persoonlijke vermogensaandelen berekend. De filter gebruikt de actuele rekeningindeling voor alle perioden, niet de rekeninggroep zoals die op de boekingsdatum was. Bronnen/imports en importstatus blijven expliciet voor alle groepen zichtbaar.

## Model, historie en privacy

- `finance_accounts` blijft het enige rekeningregister; rekeningidentiteit, bankdata en eerdere classificaties worden niet aangepast.
- `finance_wealth_groups`: alleen stabiele UUID en aanmaaktijd.
- `finance_wealth_group_events`: versleutelde naam, voorganger, actor, tijd, idempotency key en HMAC van de aanvraag. Aanmaken en hernoemen zijn append-only.
- `finance_account_group_events`: rekening-ID, nullable groep-ID, relatie, verwijzing naar het rekeningnaam-event, voorganger, actor, tijd en idempotency. Eén actuele indeling per rekening via de laatste stap. `UNASSIGNED` vereist een lege groep; `OWN`, `JOINT`, `MANAGED` vereisen een groep.
- `v_account_groups`: actuele groep/relatie voor alle rekeningen, ook zonder indelingshistorie.
- Bestaande `finance_account_name_events` worden hergebruikt. Naam en indeling worden atomair opgeslagen, met optimistic concurrency op beide actuele events. Oude naamwijzigingen via de bestaande route worden eveneens gerespecteerd.
- De UI toont de laatste 100 indelingswijzigingen met de vastgelegde rekeningnaam. Groepsnamen in die lijst zijn de huidige namen. Alle oorspronkelijke groepsnamen blijven afzonderlijk bewaard in de groepsevents.

Iedere mutatietabel blokkeert UPDATE, DELETE en TRUNCATE. Voorgangers en naam-events moeten bij dezelfde rekening/groep horen; unieke eerste events en voorgangers voorkomen vertakkingen. Een retry met dezelfde aanvraag maakt geen dubbele historie. Hergebruik van een sleutel voor andere inhoud of een verouderde versie geeft een conflict. De overzichtsquery leest een consistente, read-only PostgreSQL-snapshot, zodat lijst en totalen dezelfde indeling zien.

Alle routes gebruiken de bestaande Finance-sessie, same-origin-bescherming en no-store-responses. Er komen geen rekeningnummers of namen in logs. De groepsfilter is een presentatiefilter binnen de bestaande eigenaarssessie, geen afzonderlijke toegangsrechtenstructuur.

## Transfergrens

Er wordt geen transfermatching toegevoegd. De bestaande, expliciet aangevraagde classificatievoorstellen krijgen wel een extra grens wanneer het voorbeeld type TRANSFER heeft:

1. De bronrekening en de tegenrekening moeten beide als verschillende rekeningen in CORE bekend zijn.
2. Beide moeten dezelfde niet-lege actuele groep hebben.
3. Het voorgestelde doel moet eveneens twee rekeningen binnen diezelfde groep betreffen, en nog steeds aan de bestaande deterministische herkenningsregel voldoen.

Alleen dezelfde groep is nooit bewijs van een transfer. Een onbekende tegenrekening, overboeking naar zichzelf, niet ingedeelde rekening of grens tussen groepen levert via deze route geen transfervoorstel op. Betalingen naar bijvoorbeeld een kind of gezamenlijke rekening blijven handmatig te beoordelen. Een handmatig TRANSFER-oordeel blijft mogelijk; de app herschrijft bestaande oordelen niet wanneer de rekeningindeling wijzigt.

Bij selectie-accordering wordt deze grens opnieuw gecontroleerd. Indelingswijzigingen en reviewacceptatie delen dezelfde bestaande transactielock, zodat een tussentijdse groepswissel niet tot een verouderde acceptatie leidt. Afgekeurde aanvragen schrijven niets uit de selectie. Er zijn geen nieuwe workers, queues, externe API's of Pulse-services.

## API

- `GET /api/v1/finance/account-management`: alle gemaskeerde rekeningen, groepen en relatielabels.
- `POST /api/v1/finance/wealth-groups`: `name`, `key`.
- `POST /api/v1/finance/wealth-groups/{id}/name`: `name`, `previous`, `key`.
- `POST /api/v1/finance/accounts/{id}/management`: `name`, `group_id`, `relationship`, `previous` (indeling), `previous_name`, `key`.
- `GET /api/v1/finance/accounts/{id}/management-history`: laatste 100 indelingsevents, zonder payload-digests/idempotency-sleutels.
- `GET /api/v1/finance/data?group={uuid}` of `group=unassigned`: groepsfilter, gecombineerd met bestaande filters. Zonder group blijft het beheerde totaal zichtbaar. Een expliciete rekening buiten de groep geeft een lege doorsnede; de API verruimt filters nooit stilzwijgend.

## Installatie en rollback

Vereist de Finance-classificatiemigratie uit PR #208 en de bestaande Finance-migraties. Nieuw: `database/migrations/20260923_add_finance_wealth_groups.sql`. Voer deze eenmalig uit vóór het herstarten van het nieuwe dashboard. Geen herimport, workerherstart of nieuwe secrets nodig. Exacte NAS-commando's staan in de PR bij SCRUM-157; gebruiker doet merge, pull en deployment.

De down-migratie in `database/migrations/rollback/` werkt alleen zolang er geen groepen of indelingshistorie bestaan. Na gebruik weigert zij om gebruikersgegevens te wissen. Houd dan het schema en de historie intact. Bij terugzetten van oudere dashboardcode: gebruik geen transfer-voorstellen, omdat die code deze groepsgrens niet kent.

## Validatie en vervolgstappen

Synthetische PostgreSQL-tests dekken forward/down/forward, bestaande rekeningen zonder indeling, encryptie, retries, auth/origin, gelijktijdige naam-/indelingswijzigingen, privé/gezamenlijk/kind/nog-indelen-filters, tekstsortering, overlappende filters, transfergrenzen, groepswissels zonder reviewwijzigingen en beschermde rollback. Browsercontrole gebruikt alleen de lokale synthetische preview.

Eigendomspercentages, automatische transfermatching en historische rapportage per geldigheidsdatum blijven vervolgstappen. De huidige UI suggereert die functionaliteit niet.
