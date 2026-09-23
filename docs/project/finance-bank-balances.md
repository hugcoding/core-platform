# Banksaldi uit CAMT

Het transactietotaal is een mutatie, geen rekeningsaldo. CORE bewaart voortaan de
door de bank opgegeven OPBD- en CLBD-saldi met hun datums, per rekening en
statement. De bestaande controle `OPBD + boekingen = CLBD` blijft gelden.
Ontbrekende oudere historie vraagt geen handmatig startkapitaal als de bank een
bruikbaar saldo met peildatum levert.

## Betekenis van het overzicht

- Per geselecteerde rekening toont CORE het laatste bekende CLBD-saldo op of
  voor de einddatum van de gekozen periode. Zonder periode geldt de laatste
  beschikbare peildatum. Het bijbehorende OPBD is het beginsaldo van dat
  bankafschrift, niet noodzakelijk het beginsaldo van de gekozen filterperiode.
- Geen extrapolatie over ontbrekende perioden; de peildatum blijft zichtbaar.
  Een saldo op een oudere datum wordt nooit gepresenteerd als saldo op de
  gekozen einddatum. De begindatum filtert boekingen, niet saldoankers.
- Rekening/groep bepaalt welke banksaldi meetellen. Categorie, subcategorie,
  transactietype, sortering en paginering veranderen geen banksaldo.
- Een totaal vereist een beschikbaar, eenduidig CLBD voor elke geselecteerde
  rekening op dezelfde datum. Zolang historische extractie nog openstaat wordt
  geen totaal getoond. Deze wachttelling geldt voor alle actieve imports.
- Gelijke saldi uit overlappende exports tellen eenmaal per rekening.
  Verschillende CLBD-bedragen op dezelfde datum blokkeren het rekeningsaldo en
  totaal; er wordt geen bron stilzwijgend overschreven of gekozen.
- Alleen EUR. Ontbrekende datums, alleen DtTm-datums en omgekeerde datums geven
  geen bruikbaar anker. Er worden geen datums uit transacties geraden.
- Een groepssaldo is een som van bankrekeningen, geen persoonlijk
  eigendomsaandeel. Gezamenlijke rekeningen tellen volledig mee in hun groep.
- Het overzicht bewijst niet dat alle tussengelegen transacties zijn
  geimporteerd. De categorie- en transactietotalen blijven over de beschikbare
  boekingen gaan. De bankankers worden niet als inkomen of transactie geboekt.

## Opslag, privacy en verwerking

`finance_balance_extractions` registreert een eenmalige, versiegebonden extractie
per bestaande importbatch. `finance_bank_balances` bevat versleutelde bedragen en
datums, met account-ID, batch-ID en statementlocator; via de batch blijft het
originele source-document en bestaande CORE file-ID traceerbaar. Beide tabellen
zijn append-only, inclusief bescherming tegen TRUNCATE. De API mag alleen lezen;
alleen de ingestrol mag deze gegevens toevoegen.

Nieuwe imports bewaren saldo-evidence in dezelfde transactie als de import.
De bestaande parser/import-idempotencysleutel verandert niet. Historische
extractie leest de versleutelde, bewaarde originele XML lokaal in de bestaande
Finance-worker. Zij schrijft geen bankbestanden, transacties, reviews of nieuwe
importbatches. Geen AI, externe API, bankinhoud of bronpaden in logs.

De knop **Saldi uit bestaande imports ophalen** vraagt een `balances`-job aan in
de bestaande queue. Deze job heeft geen toegang tot de importmap nodig en is
zichtbaar via de bestaande Finance-worker in CORE Pulse. Elke bron krijgt een
eigen transactie en resource/admission-check; gecontroleerde uitvoering, hoge
CPU-/geheugen-/PostgreSQL-belasting en de CORE-pipeline houden voorrang. Herhaald
aanvragen/restarten dupliceert geen evidence. Nieuwe gewone imports vullen ook
eerst eventuele historische achterstand aan. Een historisch bestand dat de
parser niet accepteert krijgt een `unavailable`-extractiestatus, zonder wijziging
van de oorspronkelijke import. Technische fouten behouden de bestaande retries.

Terugdraaien van een import verbergt zijn saldo-evidence uit het overzicht, maar
verwijdert niets. De down-migratie weigert zodra extractiehistorie of een saldojob
bestaat. Gebruik dan een eerdere applicatieversie met behoud van het schema;
verwijder geen bron- of saldohistorie.

## Installatie op de NAS (door de beheerder)

Merge eerst de PR. Deze stappen horen in de **NAS-shell**, niet in Windows.
Voorwaarde: de Finance-migraties voor MVP, rekeningnamen, suggestie-audit,
classificatie (`20260918_add_finance_classification.sql`) en rekeninggroepen
(`20260923_add_finance_wealth_groups.sql`) zijn al toegepast.

```bash
cd /volume1/docker/nas-stack
core git pull

export CORE_FINANCE_BUILD_CONTEXT=/volume1/docker/nas-stack
core_compose() {
  /usr/local/bin/docker compose -p nas --env-file .env \
    -f docker-compose.yml \
    -f tools/runtime/finance-compose.override.yml "$@"
}

core_compose build dashboard &&
/usr/local/bin/docker exec -i postgres sh -c \
  'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d nasdb_test' \
  < database/migrations/20260923_add_finance_bank_balances.sql &&
core_compose up -d --no-build --no-deps dashboard finance_worker &&
core_compose ps dashboard finance_worker
```

De migratie is **eenmalig**. Een reeds toegepaste migratie niet opnieuw uitvoeren.
Bij een fout stopt de keten; corrigeer die voordat je containers vernieuwt.
Dashboard en Finance-worker gebruiken hetzelfde gebouwde image; beide moeten
vernieuwd worden. Geen andere workers of PostgreSQL herstarten.

Open Finance, druk **Ctrl+F5**, ontgrendel en klik eenmaal op **Saldi uit bestaande
imports ophalen**. Volg de job onder **Bronnen & imports** (of CORE Pulse). Zodra
de job gereed is, controleer per rekening het bankafschrift en de peildatum. Een
bron zonder geschikte saldi blijft als onbekend zichtbaar. Alleen opnieuw XML
importeren is niet nodig.

## Validatie

Synthetische parser- en PostgreSQL-integratietests dekken negatieve saldi,
lege afschriften, ontbrekende/ongeldige datums, overlap, conflicten, verschillende
peildatums, periodegrenzen, categorie-onafhankelijkheid, encrypted opslag,
historische aanvulling zonder nieuwe transacties, replay, importrollback,
append-only bescherming, down/up en authenticatie/CSRF. Bestaande Finance-tests
en UI-regressies blijven onderdeel van de controle. Geen echte bankdata gebruikt.
