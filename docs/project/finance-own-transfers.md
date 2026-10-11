# Overboekingen tussen CORE-rekeningen

Een nieuwe lokale indelingsronde herkent ongecategoriseerde boekingen waarvan
het aangeleverde tegenrekeningnummer exact overeenkomt met een andere bekende
CORE-rekening. Naam, bedrag en datum alleen zijn geen bewijs. Samengestelde
boekingen, reversals en afwijkend bankbewijs blijven buiten deze regel.
De lokale LLM is niet nodig. De normale centrale capaciteitscontrole blijft gelden.

De categorie is Overboekingen en het type TRANSFER, met een append-only RULE-event
en regelcode known_account_transfer. Handmatige beoordelingen gaan voor.
Bestaande categorieën worden niet overschreven. Er wordt geen tweede bankboeking
aangemaakt of een betaalpaar verzonnen wanneer de andere boeking niet geïmporteerd is.
Deze ronde verandert geen bronbestand, transactie-ID of saldo.

Het overzicht gebruikt het actuele CORE-label van de tegenrekening. Details behouden
de oorspronkelijke banknaam en omschrijving. Bij herkende transfers verschijnt
Van/Naar met het rekeninglabel en, bij verschillende groepen, de richting tussen
groepen. De actuele groepsindeling bepaalt de weergave, ook voor historische boekingen:

- dezelfde ingevulde groep: Eigen overboeking;
- verschillende groepen: Overboeking tussen groepen;
- ontbrekende groepsindeling: Overboeking tussen beheerde rekeningen.

Het filter Eigen overboekingen selecteert deze herkende TRANSFER-boekingen.
Rekening-, groeps-, periode- en categoriefilters blijven daarnaast gelden.
Tegenrekeninglabels verschijnen meteen; de transferindeling en het filter worden
beschikbaar nadat een nieuwe CORE-indelingsronde heeft gelopen.
Positieve/negatieve boekingstotalen blijven ruwe geldstromen bevatten. De aparte
inkomsten/uitgavenberekening telt TRANSFER niet mee. Banksaldi blijven de door
de bank gerapporteerde saldi, ongeacht deze categorie.

## NAS-uitrol na merge

Stop eerst een eventuele lopende indelingsjob in de UI. Opgeslagen resultaten blijven
behouden. Merge de PR, voer daarna onderstaande opdrachten uit in de NAS-shell:

```bash
cd /volume1/docker/nas-stack
core git pull --skip-docs
ls -l database/migrations/20261010_add_finance_own_transfers.sql
docker exec -i postgres sh -c \
  'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d nasdb_test' \
  < database/migrations/20261010_add_finance_own_transfers.sql
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

Vereist de bestaande Finance-migraties, inclusief 20261007_add_finance_local_rules.sql.
De lokale .env en secrets blijven ongewijzigd; Finance houdt zijn veilige default.
Vernieuw de browser. Laat LLM uit staan en start een nieuwe indelingsjob; een oude
wachtende job heeft zijn CORE-ronde al doorlopen. Geen XML-herimport nodig.
Controleer Eigen overboekingen en Lokale regels, te beoordelen. Bevestig of corrigeer
via de bestaande classificatieknop.

Rollback: database/migrations/rollback/20261010_add_finance_own_transfers.sql.
Het weigert zodra bewijs van deze nieuwe regel bestaat. Verwijder geen auditgegevens
om rollback te forceren. Stop bij problemen de worker.

Tests gebruiken uitsluitend fictieve gegevens voor beide richtingen, groepsgrenzen,
labels, filtering, bankbewijs, idempotency, eigenaarvoorrang en migratie/rollback.
Productiegegevens en oorspronkelijke bankbestanden zijn niet uitgelezen.

Met LLM uit eindigt de job na CORE als Afgerond en wordt de startknop vrijgegeven.
Ook oude wachtende LLM-jobs worden afgerond. LLM later inschakelen hervat een
afgeronde job niet; start daarvoor een nieuwe ronde. Opgeslagen categorieën blijven behouden.
