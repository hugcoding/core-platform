# CORE Pulse

CORE Pulse is het visuele operationele dashboard van het CORE-platform. Het
eerste MVP is read-only en vormt de technische basis voor het latere
interactieve CORE Control Center.

!!! info "Status van deze pagina"
    Bijgewerkt voor SCRUM-35 op **31 juli 2026**. De permanente wiki toont deze
    versie pas nadat de branch is gereviewd, gemerged en met `core docs deploy`
    opnieuw is gepubliceerd.

## Openen

CORE Pulse draait permanent op de NAS en is thuis of via OpenVPN bereikbaar:

```text
http://192.168.68.105:8080/coredashboard
```

De pagina vernieuwt de live gegevens automatisch iedere tien seconden. Met de
knop **Vernieuwen** kan dezelfde update direct handmatig worden uitgevoerd,
zonder de hele webpagina opnieuw te laden.

## Inhoud van het MVP

- Algemene platformstatus: Healthy, Attention of Degraded.
- Heartbeats van scanner, metadata-worker en watcher.
- Bereikbaarheid van PostgreSQL en Redis.
- Recente full- en intervalscans met aantallen.
- Polling-, realtime- en DLQ-wachtrijen.
- Actieve bestanden, contentgroepen, duplicaatgroepen en open events.
- Voortgang van een classification-extract-run via het checkpoint.
- NAS-opslag, geheugengebruik en systeemload.
- Snelkoppelingen naar MkDocs, Jira en GitHub.

De watcher mag bewust uitgeschakeld zijn. Het dashboard toont dit als **Paused
by policy** en niet als een technische storing.

## Publiceren

Na review en merge:

```bash
cd /volume1/docker/nas-stack
core git pull
core dashboard deploy
```

Status en URL opvragen:

```bash
core dashboard status
core dashboard open
```

`core dashboard deploy` bouwt alleen de dashboard-image, vervangt alleen de
dashboardcontainer en toont daarna diens status. Scanner, metadata-worker,
Redis, PostgreSQL en een lopende classifier worden niet herstart.

## Beveiligingsgrenzen

- De service bindt alleen aan `192.168.68.105:8080`.
- Er is geen publieke port-forward op het modem.
- Toegang verloopt via LAN of OpenVPN en wordt door de DSM-firewall beperkt.
- De container draait als non-root, read-only en met `no-new-privileges`.
- Bronexports, `/volume1` en hostinformatie zijn alleen-lezen gekoppeld.
- Het dashboard heeft geen Docker-socket.
- Het MVP bevat geen muterende HTTP-endpoints.

## Groei naar interactief Control Center

De frontend, query-API en toekomstige commandlaag zijn bewust gescheiden. Een
latere versie kan daardoor bestanden en metadata laten inspecteren, voorstellen
laten goedkeuren en toegestane scans laten aanvragen.

Maatregelen voor die commandlaag:

- vaste allowlist van acties in plaats van vrije shellcommando's;
- authenticatie en autorisatie;
- invoervalidatie en bescherming tegen browseraanvallen;
- preview/dry-run en expliciete bevestiging bij mutaties;
- asynchrone opdrachten met voortgang en resultaat;
- actor, parameters en resultaat in een auditlog.

## Actualiteit van de documentatie

De pagina's onder `docs/wiki/` en `docs/project/` zijn gereviewde
documentatiebronnen in Git. `docs/DOCUMENTATIE.md` en sommige bronoverzichten
worden gegenereerd en kunnen achterlopen totdat `core docs generate` is
uitgevoerd.

Conceptwijzigingen worden niet automatisch live gepubliceerd. Na review en
merge wordt de permanente wiki vernieuwd met:

```bash
core git pull
core docs deploy
```

Zo blijft de live documentatie stabiel, maar moet bij iedere relevante release
expliciet worden gecontroleerd dat de documentatie is meegeleverd.
