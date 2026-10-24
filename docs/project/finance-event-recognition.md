# Eventherkenner - eerste fase (SCRUM-163)

Finance heeft naast Terugkerend een knop Eventherkenner. Deze eerste fase laat
de lokale categorieherkenners, salaris, rente, bankkosten, uitkering en eigen
overboekingen zien. Voor deze bestaande herkenners toont de lijst huidige
automatische indelingen met hun model_version; handmatig vervangen indelingen
staan nog in de bestaande reviewhistorie, niet in deze actuele lijst.

De nieuwe ASN-herkenner controleert alle actieve bijschrijvingen over alle
rekeningen en perioden. Issuer ASNBANK plus bankcode 6607, positieve EUR-mutatie,
geen reversal/aggregate en geen tegenstrijdige ISO-codes betekenen ontvangen
rente. Een lege TxDtls zonder code is geen tegenstrijdig bewijs. Issuer alleen
betekent nooit dat ASN de tegenpartij is. Andere expliciete issuers worden ook
door de bestaande banktypeherkenning niet als ASN-bankcodes behandeld.

De officiële betekenis staat lokaal in core/finance/bank_code_rules.json met
bron, documentversie en controledatum. Geen runtime-download, API of LLM nodig.
De mapping levert inkomen / inkomen_rente. Wijzig bij een inhoudelijke wijziging
de regel-ID en catalogusversie, inclusief database-allowlist en tests: bestaande
review-events zijn onveranderlijk. De opgeslagen model_version
finance-local-v1:core-rule-v1:asn-interest-6607 verwijst naar catalogus asn-codes-v1.

ASN Bank wordt als herkende weergavenaam toegevoegd; bankgegevens blijven intact.
Een bevestigde merchantnaam en rekeninglabels blijven in de bestaande weergave
voorgaan. De details tonen de oorspronkelijke banktegenpartij afzonderlijk.
Voor historische payloads zonder bankcodes leest de herkenner de bestaande
versleutelde finance_record_bank_types-evidence. Hij opent geen bankexports.
De worker vult deze evidence al via zijn bestaande backfill uit bewaarde imports
aan voordat een classificatieronde loopt. Er is geen XML-herimport nodig zolang
die bron beschikbaar is. Ontbrekende codes worden in Eventherkenner gemeld;
lege/onbekende bewijsvoering krijgt geen ASN-match.

Eventherkenner is alleen-lezen. Het toont het volledige aantal matches tot de
bestaande directe scanlimiet van 25.000 bijschrijvingen en maximaal 50 voorbeelden
gelijkmatig verspreid over de periode. Boven de scanlimiet volgt een melding,
geen stilzwijgend onvolledig totaal. Je ziet banktegenpartij, rekeninglabel,
omschrijving, bedrag, huidige indeling en herkenningsbewijs. De aantallen maken
onderscheid tussen passend, handmatig beschermd/afwijkend en overige beschermde
indelingen. Dit is een lokale controle, geen algemene conflictbewakingsengine.

Bekijk transactie opent actuele transactiedetails en de bestaande beoordeling.
Indelen verloopt via de bestaande knop Ongecategoriseerde betalingen indelen.
De ASN-regel zit na menselijke voorbeelden en eigen overboekingen, voor de
bestaande inkomensfallback. De bestaande prioriteits-, categorievalidatie-,
job-idempotentie- en racebescherming blijft leidend. De preview zegt welke
betalingen in aanmerking komen; een afwijkend menselijk voorbeeld kan de
uiteindelijke uitkomst beïnvloeden. Correcte bestaande specifieke indelingen
worden niet herschreven alleen om de nieuwe regelversie vast te leggen.

Nieuwe owner-only GET-API's: /recognizers,
/recognizers/{id}/transactions en /transactions/{id}, onder /api/v1/finance.
Alleen de eigenaar ontsleutelt financiële informatie; geen plaintext index,
inhoudslogs of secrets in Git. Sluiten/vergrendelen wist de UI en negeert late
antwoorden. Geen wijziging aan Finance-enabled defaults of lokale .env.

## NAS-uitrol na merge

```sh
cd /volume1/docker/nas-stack
core git pull --skip-docs
docker exec -i postgres sh -c 'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d nasdb_test' < database/migrations/20261025_add_finance_event_recognition.sql
core finance deploy
core finance status
```

Stop bij fouten. Deze migratie breidt de bestaande databasebeveiliging alleen
uit met de expliciete ASN-regel en bewaakt categorie/type/merchant; ze wijzigt
geen transacties. Voer haar uit vóór nieuwe worker-code. Tijdens de migratie
mogen oude workers blijven werken; nieuwe code wordt pas daarna uitgerold.
Rollback weigert zodra de nieuwe regel in reviewhistorie gebruikt is.

Vernieuw de browser met Ctrl+F5. Open Eventherkenner, kies ASN-rente, controleer
bewijs en handmatige bescherming. Start desgewenst zelf een nieuwe lokale
indelingsronde met LLM uit; reeds opgeslagen beoordelingen blijven behouden.

## Validatie en vervolg

Tests gebruiken uitsluitend verzonnen XML, rekeningen en boekingen. Controleer
unit tests voor issuer/code, lege details, reversal, conflicting bewijs,
historische evidence en prioriteit; PostgreSQL-tests voor migratie/rollback,
owner-only API, append-only classificatie, historische payloads, handmatige
correcties en totaalaantallen met 50 voorbeelden. De UI-regressie is uitvoerbaar
met node tests/test_finance_event_recognition_ui.cjs. Desktop en mobiel zijn
ook met de echte HTML/CSS en fictieve antwoorden gecontroleerd.

Regels bewerken, eigen regels toevoegen, automatisch voorstellen genereren en
algemene conflictdetectie zijn expliciete vervolgfasen van Eventherkenner.
