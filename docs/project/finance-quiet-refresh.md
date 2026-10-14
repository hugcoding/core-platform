# Rustige Finance-verversing

Tijdens een wachtende/lopende job controleert Finance elke vijf minuten de API.
Zonder gewijzigde overzichtsgegevens worden alleen voortgang en actieknoppen
bijgewerkt. Geen laadmelding of herbouw van filters/transactierijen voor een
ongewijzigde achtergrondcontrole. Ook als andere onderdelen wijzigen, worden
identieke transactierijen behouden. Bij afronding stopt de automatische controle.

De bestaande knop Vernieuwen blijft staan en haalt direct gegevens op. Filters,
sorteren en opslaan blijven eveneens direct werken. Een externe wijziging kan
maximaal ongeveer vijf minuten plus aanvraagtijd later zichtbaar worden; gebruik
Vernieuwen voor directe controle. Dit gebruikt polling, geen server-push.
De extra rijcache wordt gewist bij vergrendelen. Geen nieuwe opslag, API of
databasewijziging en geen wijziging aan LLM/worker-verwerking.

## NAS-uitrol

Merge de PR en voer in de NAS-shell uit:

```bash
cd /volume1/docker/nas-stack
core git pull --skip-docs
export CORE_FINANCE_BUILD_CONTEXT=/volume1/docker/nas-stack
core_compose() {
  /usr/local/bin/docker compose -p nas --env-file .env \
    -f docker-compose.yml \
    -f tools/runtime/finance-compose.override.yml "$@"
}
core_compose build dashboard
core_compose up -d --no-deps --force-recreate dashboard
core_compose ps dashboard
core doctor --finance
```

Als pull lokale wijzigingen meldt: behoud ze en commit of bewaar ze eerst apart.
Geen reset/clean gebruiken. Geen migratie of worker-rebuild nodig.
Vernieuw daarna met Ctrl+F5. Controleer tijdens een job dat voortgang bij de
vijfminutencontrole verandert terwijl ongewijzigde transactierijen blijven staan.
Vernieuwen moet direct werken en de automatische controle stopt bij afronding.

Validatie: JavaScript-syntax, synthetische achtergrond-refresh (ongewijzigd,
wijzigingen, minimuminterval, afronding, handmatige knop) en bestaande filter-,
fase- en LLM-toggle-UI-tests. Geen productiegegevens gelezen of deployment gedaan.
