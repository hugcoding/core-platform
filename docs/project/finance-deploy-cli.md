# Permanente Finance-commando's

Vanaf deze wijziging zijn de tijdelijke export van CORE_FINANCE_BUILD_CONTEXT
en de handmatig gedefinieerde core_compose-functie niet meer nodig.

```bash
core finance deploy
core finance status
```

Beide commando's bepalen de repositorymap vanaf de wrapper en gebruiken:
Compose-project nas, de lokale .env, docker-compose.yml,
tools/runtime/finance-compose.override.yml en profiel finance. Het buildpad wordt
voor de aanroep automatisch op deze repositorymap gezet, ook in een nieuwe
SSH-sessie. Een oude handmatig geëxporteerde buildcontext wordt niet gebruikt.

Deploy bouwt dashboard en finance_worker, vervangt alleen die twee services met
--no-deps --force-recreate, toont hun status en voert de bestaande Finance-doctor
uit met dezelfde Compose-configuratie en maximaal 20 seconden wachttijd.
Status bouwt of herstart niets: het toont de services en voert de diagnose uit.
Een build-, vervangings- of diagnosefout geeft een foutcode terug.

De lokale CORE_FINANCE_ENABLED-instelling blijft leidend; Finance wordt niet
automatisch aangezet. De veilige default false, lokale .env en secrets worden
niet veranderd. Diagnostiek toont geen secretwaarden. Deze CLI voert geen Git-
pulls, database-migraties, imports of classificatierondes uit. Eventuele migraties
uit een feature-PR moeten voor deployment afzonderlijk worden uitgevoerd.

## Eerste installatie op de NAS

Merge de PR. Voer daarna in de NAS-shell uit:

```bash
cd /volume1/docker/nas-stack
core git pull --skip-docs
core finance deploy
core finance status
```

Stop bij fouten. Als pull lokale wijzigingen meldt: bewaar of commit die eerst;
geen reset/clean gebruiken. Geen extra installatie of shellprofielwijziging nodig.
De reeds gebruikte core-alias blijft dezelfde wrapper aanwijzen.
Vernieuw de browser met Ctrl+F5 als dashboardbestanden veranderd zijn.

Daarna bestaat de normale uitrol uit core git pull --skip-docs, eventuele
feature-migratie en core finance deploy. Voor alleen een controle volstaat
core finance status. Hiervoor is geen databasemigratie toegevoegd.

## Validatie

Shell-tests gebruiken uitsluitend nep-Docker en een nep-doctor: juist buildpad,
project/profiel/env/Compose-bestanden, beperkte servicescope, foutpropagatie,
alleen-lezen status, argumentvalidatie en behoud van lokale instellingen.
De bestaande Git-wrapper- en Finance-doctortests blijven gelden. Geen echte
productiebuild, containervervanging, pull, import of databasemutatie uitgevoerd.
