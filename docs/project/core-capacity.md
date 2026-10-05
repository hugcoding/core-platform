# Centrale CORE-capaciteitsmeting

`capacity_worker` meet iedere vijf seconden de NAS-CPU en het beschikbare geheugen.
Alleen deze collector leest `/host/proc`. Hij publiceert een versiegebonden JSON-snapshot
in Redis (`core:capacity:v1`, TTL 20 seconden). Pulse, Finance, Workset AI, OCR en
gecontroleerde uitvoering lezen deze snapshot via `core.runtime.capacity`.

CPU is het verschil tussen twee aggregate `/proc/stat`-samples, op een schaal van
0 tot 100% over alle cores. Guest-tijd wordt niet dubbel geteld; idle en iowait
tellen niet als bezette CPU. Load average blijft afzonderlijk zichtbaar in Pulse,
maar is geen CPU-percentage en wordt niet meer gebruikt als CPU-grens.

De bestaande Pulse-geheugencorrectie blijft gelden: `MemAvailable` waar beschikbaar,
anders `MemFree + max(0, Buffers + Cached + SReclaimable - Shmem)`, begrensd op het
totale geheugen. Er worden geen bankgegevens of database-inhoud verzameld.

Bij opstart zijn twee CPU-samples nodig (circa vijf seconden). Ontbrekende,
ongeldige of verouderde snapshots geven `capacity_unavailable`; workers beginnen
dan geen nieuw werk. Een meetfout verwijdert de snapshot; bij uitval vervalt deze
automatisch. Pulse toont ontbrekende waarden als niet beschikbaar en toont de collector
bij de services. Er is geen lokale fallbackberekening in de afnemers.

De meting is gedeeld; beleid blijft per workload instelbaar. CPU-defaults zijn
Finance 60%, OCR 60%, automatische AI 70%, gecontroleerde uitvoering 80%.
`CORE_EXECUTION_MAX_CPU_PERCENT` vervangt `CORE_EXECUTION_MAX_LOAD_PER_CPU`;
een oude loadgrens is niet numeriek om te rekenen naar CPU-gebruik.
De bestaande uitzondering voor expliciet aangevraagde AI-taken blijft gelden.
Geheugengrenzen, wachtrijprioriteit, databasechecks, gecontroleerde uitvoering en
de stabiliteitswachttijd van Finance blijven behouden. Deze wijziging centraliseert
de hostmeting; ze maakt nog geen centrale scheduler of reserveringssysteem.

## Installatie op deze NAS na merge

Geen SQL-migratie, wachtwoordwijziging of herimport nodig. Voer dit uit als geen
gecontroleerde uitvoering actief is. Onderstaande stappen gebruiken de bestaande
Finance Compose-override en gedeelde dashboardimage.

1. Open de NAS-shell en haal de gemergde wijzigingen op:

```sh
cd /volume1/docker/nas-stack
core git pull
export CORE_FINANCE_BUILD_CONTEXT=/volume1/docker/nas-stack
core_compose() {
  /usr/local/bin/docker compose -p nas --env-file .env \
    -f docker-compose.yml \
    -f tools/runtime/finance-compose.override.yml "$@"
}
```

2. Bouw de vier images. Collector en Finance gebruiken dezelfde image als dashboard:

```sh
core_compose build dashboard workset_ai_worker workset_ocr_worker controlled_execution_worker
```

3. Start eerst de centrale collector en controleer de status:

```sh
core_compose up -d --no-build --no-deps capacity_worker
core_compose ps capacity_worker
```

Wacht tot `healthy` verschijnt (doorgaans binnen 20 seconden; herhaal `ps`).
Start de afnemers pas daarna. Blijft de collector ongezond, ga niet verder.

4. Start de bijgewerkte afnemers:

```sh
core_compose up -d --no-build --no-deps dashboard finance_worker workset_ai_worker workset_ocr_worker controlled_execution_worker
core_compose ps capacity_worker dashboard finance_worker workset_ai_worker workset_ocr_worker controlled_execution_worker
```

5. Vernieuw Pulse en Finance met Ctrl+F5. Pulse toont CPU als percentage naast
load average. Finance kan nog wachten op zijn bestaande stabiliteitscontrole,
drukke PostgreSQL of gecontroleerde uitvoering; 127% CPU kan deze meting niet opleveren.

Bij terugdraaien: revert de PR via GitHub, haal die revert met `core git pull` op,
bouw dezelfde vier images opnieuw en start de vijf afnemers opnieuw. De ongebruikte
collector kan daarna worden gestopt met
`/usr/local/bin/docker stop nas-capacity_worker-1`. Er is geen datarollback nodig.

## Validatie

`tests/test_capacity.py` controleert CPU-delta's, cachegeheugen, Redis-verval,
ongeldige snapshots, collector-warmup en wachtgedrag van alle vier workers.
De Pulse-contracttests controleren dat dezelfde snapshot wordt getoond en
ontbrekende waarden niet als nul worden weergegeven. Alleen synthetische data.

## Centrale CPU-toelating

De collector houdt de CPU-historie centraal bij. Workers lezen dezelfde toestand uit Redis; er komen geen lokale tellers of hostmetingen. Pulse toont per profiel dezelfde CPU-toelating.

Standaard: pauze bij 5 van 6 metingen boven de grens; hervatten na 30 seconden aaneengesloten onder de lagere hervatgrens. Metingen komen ongeveer iedere 5 seconden. Meetgaten tellen niet als herstel. Een lopende batch wordt niet afgebroken.

| Profiel | Pauzegrens | Hervatgrens |
|---|---:|---:|
| Finance | 60% | 50% |
| Automatische AI | 70% | 60% |
| OCR | 60% | 50% |
| Gecontroleerde uitvoering | 80% | 70% |

Lokaal instelbaar, doorgegeven aan capacity_worker:

```dotenv
CORE_CPU_WINDOW_SAMPLES=6
CORE_CPU_HIGH_SAMPLES=5
CORE_CPU_RESUME_SECONDS=30
CORE_FINANCE_MAX_CPU_PERCENT=60
CORE_FINANCE_CPU_RESUME_PERCENT=50
```

Andere profielen gebruiken dezelfde CORE_AI_, CORE_OCR_ en CORE_EXECUTION_ instellingen. Hervatgrens lager dan pauzegrens; hoge metingen niet groter dan venster. Ongeldige configuratie stopt de collector en capaciteit wordt unavailable. Lokale .env en secrets horen nooit in Git.

Geheugen, PostgreSQL, prioriteiten en gecontroleerde uitvoering blijven afzonderlijke checks. Expliciete AI-taken behouden hun CPU-uitzondering; Pulse toont de algemene profieltoestand.

Tijdens een gefaseerde uitrol met een oude collector blijft tijdelijk de oude momentane CPU-regel gelden. Dat is compatibiliteit, zonder lokale historie. Bouw collector en alle afnemers daarom samen. Geen migratie nodig.
