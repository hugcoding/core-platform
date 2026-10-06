# Bankinformatie voor transactietypes — SCRUM-162, eerste slice

CORE herkent het transactietype zonder LLM uit gestructureerde CAMT-informatie.
Pinbetalingen zijn uitgaven; kaartterugbetalingen en expliciete terugboekingen
zijn correcties. Bekende ASN-incasso-, bankkosten- en rentecodes krijgen een
bijpassend type. Een categorie wordt door deze regels niet ingevuld.

De eerste regels gebruiken de openbare [ASN CAMT-specificatie](https://www.asnbank.nl/downloads/formaatbeschrijving-camt053.html)
en [ASN transaction codeset v2.0](https://openbanking.asnbank.nl/build/image/pdf/transaction_codeset_asn_bank_ais_api_documentation_v2.0.pdf).
Viercijferige codes gelden uitsluitend voor ASN/SNS/RegioBank-rekeningen.
Ondersteunde ISO-bankcodes zijn bankonafhankelijk. Vrije omschrijvingstekst
wordt niet als bankcode geïnterpreteerd.

Cashopnames, algemene overboekingen, ontbrekende codes, meerdere onderliggende
transacties en tegenstrijdige bewijzen blijven onbekend. Een bijschrijving is
niet automatisch inkomen; een SEPA-overboeking bewijst geen eigen overboeking.
Eigen rekeninggroepen en ontvangst van bijvoorbeeld salaris volgen later.

## Opslag en voorrang

`finance.finance_record_bank_types` bevat append-only, versiegebonden evidence
per bestaand importrecord. De oorspronkelijke bankcodes blijven versleuteld.
Bron, importbatch en bronregel blijven via het bestaande record terug te vinden.
Transactiefingerprints, duplicaatsleutels en originele bankbestanden veranderen
niet. De bestaande `finance.v_transactions` gebruikt het banktype alleen zonder
een opgeslagen beoordeling; bestaande automatische en menselijke beoordelingen
worden niet herschreven. De UI noemt deze bron **bankinformatie**.

Nieuwe imports schrijven dit bewijs meteen. De bestaande acties **XML-map
inlezen**, **ASN-herkenning/reconciliatie** en **Ongecategoriseerde betalingen
indelen** lezen oudere, bewaarde bronnen lokaal opnieuw voor deze metadata.
Er ontstaan geen extra imports of transacties. De worker controleert de centrale
capaciteitsmeting per bron. CORE Pulse krijgt status `bank_type_recognition`.
Alleen de categoriseringsactie kan vervolgens de lokale LLM gebruiken; voor
deze bankherkenning zelf is geen LLM nodig.

Nieuwe automatische categorieën mogen niet botsen met een bewezen banktype.
Handmatige beoordelingen behouden hun voorrang. Voor categorieherkenning is
dit een eerste fundament: uitbreiding van merchantregels en hergebruik van
menselijke categorieën is een volgende slice.

## Uitrol op de NAS

Merge de PR in GitHub. Voer daarna uit in de NAS-shell:

```bash
cd /volume1/docker/nas-stack
core git pull --skip-docs
ls -l database/migrations/20261006_add_finance_bank_types.sql
docker exec -i postgres sh -c \
  'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d nasdb_test' \
  < database/migrations/20261006_add_finance_bank_types.sql
export CORE_FINANCE_BUILD_CONTEXT=/volume1/docker/nas-stack
core_compose() {
  /usr/local/bin/docker compose -p nas --env-file .env \
    -f docker-compose.yml \
    -f tools/runtime/finance-compose.override.yml "$@"
}
core_compose build dashboard finance_worker
core_compose --profile finance up -d --no-deps --force-recreate dashboard finance_worker
core_compose --profile finance ps dashboard finance_worker
core doctor --finance --worker
```

Behoud de bestaande lokale Finance-configuratie en secrets. Stop een actieve
categoriseringsjob via de UI voordat je de containers vervangt. Eerder opgeslagen
oordelen blijven behouden. Vernieuw de browser en start ASN-herkenning voor de
bestaande imports. Controleer daarna een ongecategoriseerde pinbetaling: type
Uitgaven, bron bankinformatie, categorie nog open. Controleer ook een handmatig
ingedeelde betaling: het oordeel blijft gelijk.

Een privacyvriendelijke controle zonder bankinhoud:

```bash
docker exec -i postgres sh -c \
  'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d nasdb_test' <<'SQL'
SELECT transaction_type, reason_code, count(*)
FROM finance.finance_record_bank_types GROUP BY 1,2 ORDER BY 1,2;
SELECT transaction_type, classification_source, count(*)
FROM finance.v_transactions GROUP BY 1,2 ORDER BY 1,2;
SQL
```

Rollbackbestand: `database/migrations/rollback/20261006_add_finance_bank_types.sql`.
Het verwijdert het schema alleen zolang er nog geen evidence is opgeslagen;
anders weigert het met `finance_bank_type_evidence_present`. Bij problemen na
gebruik: stop de worker en herstel de vorige applicatieversie, met behoud van
de database en opgeslagen evidence. Geen bewijs verwijderen om rollback te forceren.

## Tests

Synthetische tests controleren codes, betaalrichting, terugboekingen,
onthouding, ongewijzigde fingerprints, import/backfill/replay, eigenaarvoorrang,
append-only-beveiliging en forward/rollback/forward op een lege database.
Integratietests gebruiken uitsluitend `core_finance_test`; geen productiegegevens.
