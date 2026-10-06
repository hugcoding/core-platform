# Lokale LLM aan/uit en lokale categorieherkenning — SCRUM-162

In **Automatische indeling** staat **Lokale LLM aan**. Uitschakelen bewaart
de voorkeur in de database en laat CORE zijn herkenningsronde uitvoeren.
Daarna blijven de overige targets in dezelfde job wachten met reden
`llm_disabled`. Inschakelen laat die job verdergaan zodra de NAS-capaciteit
dat toelaat. De voorkeur blijft behouden na herladen of containervervanging.
Een al verzonden LLM-aanvraag kan afronden, maar mag na uitschakelen geen
nieuw resultaat publiceren. Eerder opgeslagen indelingen blijven behouden.

De instellingen staan append-only in
`finance.finance_classification_settings_events`; alleen de ontgrendelde
eigenaar kan ze via de bestaande Finance-beveiliging wijzigen. Zonder
instellingshistorie blijft LLM aan voor bestaande installaties. De veilige
Finance-activatie-default in Compose blijft **false**.

CORE kan nu zonder LLM-configuratie categorieën hergebruiken. Herkenbare
pinomschrijvingen van Lidl, Jumbo, Aldi, Dekamarkt, Kruidvat, Etos, Wibra
en HEMA worden over filialen heen aan dezelfde winkel gekoppeld. Categorieën
komen uitsluitend uit handmatige beoordelingen. Bij tegenstrijdige voorbeelden
blijft de betaling open. Vrije factuurtekst stelt geen nieuwe winkelidentiteit
vast. De herkenningsversie is `local-merchant-v3`; oude beoordelingen blijven
ongewijzigd aanwezig. Dit breidt ook de bestaande soortgelijke voorstellen uit.

## Uitrol door eigenaar

Stop de huidige categoriseringsjob via **Stoppen** voordat je de containers
vervangt. Merge de PR in GitHub en voer op de NAS uit:

```bash
cd /volume1/docker/nas-stack
core git pull --skip-docs
ls -l database/migrations/20261006_add_finance_llm_toggle.sql
docker exec -i postgres sh -c \
  'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d nasdb_test' \
  < database/migrations/20261006_add_finance_llm_toggle.sql
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

Behoud de lokale `.env` en secrets. De banktype-migratie uit PR #227 moet al
aanwezig zijn; deze PR voegt één nieuwe migratie toe.

Vernieuw de browser, zet **Lokale LLM aan** uit en start
**Ongecategoriseerde betalingen indelen**. CORE werkt eerst; daarna toont de
job **LLM uit** en wachten resterende betalingen. Een bestaande menselijke
categorie voor een ondersteunde winkel kan nu ook andere filialen helpen.
Zet LLM later aan om de resterende job te hervatten. De centrale capaciteit
en workercontroles kunnen hervatting vertragen.

Een wachtende job houdt de bestaande enkele verwerkingsplek bezet. Kies
**Stoppen** als je een andere import of een nieuwe CORE-ronde wilt starten.
Na een volgende herkenningsverbetering: stop de oude wachtende job, laat LLM
uit staan en start een nieuwe indeling. Zo worden resterende betalingen opnieuw
aan de verbeterde CORE-regels aangeboden. Geen XML-herimport nodig.

Controle zonder bankinhoud:

```bash
docker exec -i postgres sh -c \
  'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d nasdb_test' <<'SQL'
SELECT llm_enabled FROM finance.v_classification_settings;
SELECT status,categorization_phase,waiting_reason
FROM finance.finance_ingest_jobs WHERE job_kind='categorize'
ORDER BY requested_at DESC LIMIT 1;
SQL
```

Rollback: `database/migrations/rollback/20261006_add_finance_llm_toggle.sql`.
Deze weigert zodra er instellingenhistorie of v3-classificatiebewijs bestaat.
Verwijder geen historie om rollback te forceren; stop de worker en herstel bij
problemen de vorige applicatieversie met behoud van database en bewijs.

Tests gebruiken uitsluitend synthetische gegevens en een geïsoleerde database.
Ze controleren CORE zonder model, pauzeren, hervatten, uitschakelen tijdens
een aanvraag, herhaalde instellingen, filialen, verkeerde context, UI-status
en forward/rollback/forward.
