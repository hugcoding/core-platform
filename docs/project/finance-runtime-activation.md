# Finance runtime-activatie (SCRUM-159)

Finance staat standaard **uit**. Een installatie die Finance gebruikt, zet expliciet
in de lokale `/volume1/docker/nas-stack/.env`:

```dotenv
CORE_FINANCE_ENABLED=true
```

Dit is deployment/runtime-configuratie, geen productie-instelling in Git. Pas alleen
deze regel aan met je lokale editor; vervang niet het hele `.env`-bestand. Ook de
Finance-buildoverride neemt nu deze instelling over: die activeert Finance niet meer
zelf. Een shellvariabele heeft volgens Compose voorrang op `.env`.

`.env`, lokale `.env.*`-varianten en Finance-secretbestanden zijn genegeerd door Git
en uitgesloten van de Docker-buildcontext. De bestaande sleutels blijven buiten de
repository, in `/volume1/docker/core-runtime/finance`. Verander of regenereer ze niet
voor een rebuild. Een `.env.example` mag uitsluitend fictieve voorbeeldwaarden bevatten.

De bestaande `core git pull` doet een fetch en fast-forward merge, zonder clean/reset
of het kopieren van `.env`. Gewone Git-pulls, Compose-builds en containerrecreaties
schrijven de genegeerde lokale `.env` niet. Rebuilds lezen de actuele runtime-instelling;
een build alleen wijzigt de omgeving van een reeds draaiende container niet.

## Uitrollen op de NAS

Na merge van de PR, in de **NAS-shell**:

```bash
cd /volume1/docker/nas-stack
core git pull --skip-docs
```

Controleer met je lokale editor dat `.env` de bovenstaande regel bevat. Plaats geen
kopie van `.env` of secretwaarden in een PR, chat of ticket. Daarna:

```bash
/usr/local/bin/docker compose --profile finance build dashboard finance_worker
/usr/local/bin/docker compose --profile finance up -d --no-deps --force-recreate dashboard finance_worker
core doctor --finance --worker
```

Werk bij deze eerste update beide images bij: een oude worker bevat de diagnosemodule
nog niet. Voor latere dashboardupdates kun je `core dashboard deploy` gebruiken;
dat bouwt, recreeert en valideert automatisch. Op een installatie zonder Finance-worker
volstaan `core dashboard deploy` en `core doctor --finance`.

Geen migratie, herimport of nieuwe secrets nodig. Vernieuw vervolgens Finance in
je browser en ontgrendel met je bestaande toegangscode.

## Diagnose en deploymentcontrole

```bash
core doctor --finance
```

Toont `configured`, de bedoelde `enabled`-waarde, de werkelijke dashboardwaarde,
secrets, database en storage. De databasecontrole gebruikt de bestaande Finance-rol
en een read-only query met `LIMIT 0`; er worden geen transacties of bronbestanden
gelezen. De secretcontrole valideert beschikbaarheid en structuur, niet of een
vervangen sleutel bestaande data nog kan ontsleutelen.

- Ontbrekend/leeg: `configured: no`, `enabled: false` en een waarschuwing over de
  veilige default. Een bewust uitgeschakelde installatie vereist geen Finance-secrets.
- Verschil tussen lokale instelling, Compose-override en container: foutstatus en
  advies om met de bedoelde configuratie te recreeren; niets wordt automatisch aangepast.
- Actieve Finance met ontbrekende/ongeldige secrets, database/schema of importmap:
  foutstatus, zonder waarden, exceptionteksten of bankgegevens.
- Een gestopte worker geeft een waarschuwing; `--worker` maakt zijn aanwezigheid
  verplicht. Een draaiende worker wordt altijd gecontroleerd.

Exitcode `0` betekent dat de gecontroleerde configuratie overeenkomt; `1` vereist
actie. Een oude container zonder de diagnosemodule geeft `unavailable`; rebuild en
recreate die service. `--wait 20` laat net gestarte containers kort opkomen.
De bestaande `core dashboard deploy`, `core runtime start/restart` en
`tools/runtime/rebuildall` controleren na het opstarten en stoppen bij een fout.
Ze zetten Finance nooit zelf aan en draaien een mislukte deployment niet automatisch terug.

Bij handmatige Compose-commando's voer je de diagnose zelf uit na `up`. Gebruik
dezelfde bestanden, projectnaam en env-file als bij de deployment, bijvoorbeeld:

```bash
export CORE_FINANCE_BUILD_CONTEXT=/volume1/docker/nas-stack
core doctor --finance -p nas --env-file .env \
  -f docker-compose.yml -f tools/runtime/finance-compose.override.yml --worker
```

De check verandert geen `.env`, secrets, database of containers. Gebruik geen ruwe
`docker inspect`- of `compose config`-output als deelbare diagnose: die kan secrets bevatten.
