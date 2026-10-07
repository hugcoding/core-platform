# Brede lokale categorieherkenning — SCRUM-162

CORE past brede categorieën toe zonder dat eerst een handmatig voorbeeld of
LLM nodig is. Dit gebeurt uitsluitend bij betalingen zonder categorie en zonder
bevestigd eigenaarsoordeel. De volgorde is: menselijke voorbeelden, brede lokale
regels, en alleen indien ingeschakeld de lokale LLM voor resterende groepen.

De regels herkennen bekende namen en bedrijfstypen voor levensmiddelen,
vervoer/fietsen, restaurants, energie/water, telecom/digitale diensten,
verzekeringen, kleding en huishoudwinkels. De eerste indeling is een
hoofdcategorie; CORE verzint geen precieze aankoop of subcategorie. UWV-
bijschrijvingen krijgen breed Inkomsten. Vastgelegde bankrente en bankkosten
gebruiken hun bankbewijs. Deze herkenning bewijst geen maandelijks abonnement
en maakt geen forecast.

Tegenpartijnamen, bestaande kaartvelden en bedrijfsdomeinen leveren het bewijs.
Een vrije omschrijving met alleen woorden zoals 'fiets' of 'supermarkt' is
onvoldoende. Een private ontvanger wordt niet op basis van een winkelnaam in
zijn omschrijving ingedeeld. Betaalproviders krijgen zelf geen categorie.
Niet-herkende, conflicterende en samengestelde boekingen blijven open.
Bijschrijvingen van winkels worden alleen als correctie behandeld wanneer
bankinformatie dat ondersteunt; ze worden niet vanzelf inkomen.

Automatische events hebben bron `RULE`, `confirmed=false` en een versiegebonden
regelcode in `model_version`. De bestaande append-only reviews, eigenaarvoorrang,
bronverwijzingen en centrale capaciteitscontrole blijven gelden. De bronbestanden
en transactiefingerprints veranderen niet. Ontbrekende of heringedeelde categorieën
worden niet automatisch aangemaakt of overschreven.

Een correctie voor een herkend bedrijf kan ook zonder tegenrekeningnummer als
menselijk voorbeeld worden hergebruikt. Daarbij gebruikt CORE de exacte
bedrijfsidentiteit, geen algemene soort zoals 'alle fietsenwinkels'. Dat werkt
ook in de bestaande soortgelijke voorstellen, met versie `local-merchant-v4`.
Bij tegenstrijdige menselijke voorbeelden wint de brede regel niet alsnog.

## Beoordelen

Kies in het overzicht **Indeling → Lokale regels, te beoordelen**. Open een
betaling om de categorie te bevestigen of te wijzigen met de bestaande
opslagknop. De rij en historie tonen de lokale regel. Een handmatig opgeslagen
oordeel verdwijnt uit dit reviewfilter; het oorspronkelijke automatische event
blijft aanwezig. Andere filters blijven werken. **Alle automatische indelingen**
toont ook de bestaande indelingen uit menselijke voorbeelden en de LLM.

De jobstatus vermeldt afzonderlijk het aantal betalingen dat CORE heeft bekeken
en het aantal afgeronde resultaten. Wanneer LLM uit staat, kan CORE de volledige
ronde bekeken hebben terwijl resterende targets wachten.

## Uitrol op de NAS

Stop de huidige indelingsjob via de UI. Opgeslagen categorieën blijven behouden.
Merge de PR in GitHub, en voer daarna in de NAS-shell uit:

```bash
cd /volume1/docker/nas-stack
core git pull --skip-docs
ls -l database/migrations/20261007_add_finance_local_rules.sql
docker exec -i postgres sh -c \
  'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d nasdb_test' \
  < database/migrations/20261007_add_finance_local_rules.sql
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

De eerdere migraties uit PR #227 en #228 moeten al zijn uitgevoerd. Behoud de
lokale `.env` en secrets. Vernieuw daarna de browser, laat LLM uit staan en start
een **nieuwe** indelingsjob. De oude wachtende job heeft zijn CORE-ronde al gedaan
en past deze nieuwe regels niet vanzelf opnieuw toe. Geen XML-herimport nodig.
Bekijk na verwerking het nieuwe reviewfilter en corrigeer waar nodig.

Controle zonder bankinhoud:

```bash
docker exec -i postgres sh -c \
  'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d nasdb_test' <<'SQL'
SELECT category_code,model_version,count(*)
FROM finance.v_transactions
WHERE classification_source='RULE' AND NOT confirmed AND category_code IS NOT NULL
GROUP BY 1,2 ORDER BY 3 DESC;
SQL
```

Rollbackbestand: `database/migrations/rollback/20261007_add_finance_local_rules.sql`.
Het weigert zodra lokale-regelreviews of v4-bewijs bestaan, om historie te behouden.
Stop bij problemen de worker; verwijder geen bewijs om rollback te forceren.

## Validatie en bereik

Tests gebruiken synthetische betalingen en een geïsoleerde PostgreSQL-database.
Ze controleren brede regels zonder LLM, privémemo's, bankrichting, onbekende
bedrijven, conflicten, aangepaste categorieën, leren van eigenaarcorrecties,
reviewfilter, audit en migraties/rollback. Werkelijke dekking hangt van de
tegenpartijen en exports af; er is geen beloofd indelingspercentage. Deze ronde
gebruikt geen externe API, internetzoekactie of cloud-AI.
