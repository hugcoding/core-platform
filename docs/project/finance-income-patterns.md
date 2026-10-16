# Herbruikbare inkomenspatronen

Een nieuwe indelingsronde gebruikt bevestigde menselijke beoordelingen als
eerste bron voor salaris en ontvangen rente. De regel wordt afgeleid uit de
bestaande reviews; er is geen tweede leerregister. Een nieuwe review of conflict
werkt daardoor door in een volgende ronde. Er is geen LLM of bedrijfs-API nodig.

- Salaris: positieve boeking, expliciete salaris/loon-omschrijving en bruikbare
  banktegenpartij. Het patroon omvat de ontvangende rekening, valuta, werkgever
  en aangeleverde tegenrekening. Maand, jaar, persoonlijke toevoegingen en bedrag
  zijn geen sleutel. Meerdere betalingen per maand zijn toegestaan. Dit is geen
  abonnementherkenning of forecast.
- Rente: positief saldo-rentepatroon of gestructureerd bewijs van ontvangen rente,
  begrensd tot dezelfde rekening en valuta. Een wisselende datum of ontbrekende
  banknaam verhindert het patroon niet. Een bevestigde merchantnaam kan uit het
  eigenaarsoordeel worden hergebruikt; bankbronvelden blijven ongewijzigd.
- Zonder menselijk voorbeeld kunnen sterke salaris/rentesignalen de bestaande
  categorieën Inkomen/Salaris en Inkomen/Rente toepassen. Ontbrekende of anders
  ingedeelde categorieën worden niet verzonnen of automatisch aangepast.

Tegenstrijdige menselijke voorbeelden blokkeren de automatische indeling van
dat patroon. Afboekingen, reversals, betaalproviders, samengestelde boekingen en
andere inkomensdoelen worden niet door een salarispatroon meegenomen. Een naam
of bedrag alleen is geen patroonbewijs. Controleer automatische indelingen:
een salarisomschrijving is een sterk signaal, geen geverifieerde loonstrook.

## Verfijnen

Naast betalingen zonder categorie komen grove automatische RULE/MERCHANT/AI-
indelingen zonder subcategorie in aanmerking. Verfijning mag alleen een
subcategorie toevoegen binnen dezelfde hoofdcategorie en hetzelfde type.
Er wordt geen bestaande specifieke of handmatige indeling vervangen. LLM krijgt
geen verfijningstaak. De huidige lokale merchant-herkenning kan eveneens een
bevestigde subcategorie binnen dezelfde hoofdcategorie hergebruiken.

Elke verandering is een nieuw append-only reviewevent. Hergebruik van een
inkomenspatroon bewaart source_review_id en suggestion_method=income-pattern-v1.
De UI toont daarbij 'jouw bevestigde inkomenspatroon'. Regels zonder voorbeeld
hebben RULE als bron. Een volgende ronde schrijft geen extra event wanneer de
betaling inmiddels specifiek of handmatig beoordeeld is. Bestaande capaciteit-
en LLM-uit/afrondingslogica blijven gelden.

## NAS-uitrol

Stop eventueel de lopende indelingsronde via de UI. Merge de PR en voer daarna
de volgende opdrachten uit in de NAS-shell. Bij een fout stoppen.

```bash
cd /volume1/docker/nas-stack
core git pull --skip-docs
ls -l database/migrations/20261016_add_finance_income_patterns.sql
docker exec -i postgres sh -c \
  'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d nasdb_test' \
  < database/migrations/20261016_add_finance_income_patterns.sql
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

Vereist alle bestaande migraties tot en met 20261010_add_finance_own_transfers.sql.
De lokale .env en secrets blijven behouden. Als pull lokale wijzigingen meldt,
bewaar of commit die eerst; geen reset/clean. Vernieuw de browser met Ctrl+F5 en
start een nieuwe indelingsronde met LLM uit. Geen XML-herimport nodig.

De aantallen kunnen nu ook verfijningen omvatten. Controleer Inkomen/Salaris,
Inkomen/Rente en de bestaande filters voor automatische indelingen. Handmatig
bevestigen of corrigeren werkt zoals eerder. De normale vijfminutencontrole en
de knop Vernieuwen blijven gelden.

Rollback: database/migrations/rollback/20261016_add_finance_income_patterns.sql.
Deze weigert als inkomen-patroonbewijs of salarisregelevents bestaan. Verwijder
geen historie om rollback te forceren; stop bij problemen de worker.

## Meten zonder bankinhoud

```sql
SELECT classification_source,rule_version,model_version,count(*)
FROM finance.v_transactions
WHERE category_code IS NOT NULL AND NOT confirmed
GROUP BY 1,2,3 ORDER BY count(*) DESC;
```

Bronnen en reviewhistorie onderscheiden menselijke voorbeelden, regels en LLM.
Deze eerste ronde voegt geen ML-model, apart statistiekdashboard of externe
opzoekdienst toe. Tests gebruiken fictieve gegevens; productie-bankbestanden,
omschrijvingen en rekeningnummers zijn niet uitgelezen.
