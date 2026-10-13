# Gedeelde CORE Git-verbinding

`core git pull` liep via een aparte Docker-aanroep, zonder de SSH-key,
known_hosts en gebruikersmapping die andere Git-commando's wel gebruikten.
Alle Git-aanroepen gebruiken nu tools/runtime/git-run. Dit behoudt de bestaande
SSH-instellingen, argumentgrenzen, veilige directory en ondersteuning van
CORE_GIT_IMAGE. Secretwaarden worden niet getoond of in Git opgeslagen.

Pull behoudt de bestaande controles: geen bijgehouden lokale wijzigingen,
fetch origin/main, uitsluitend fast-forward merge, documentatie alleen na
expliciete keuze of --rebuild-docs. --skip-docs blijft werken. De lokale .env
en ongerelateerde bestanden worden niet verwijderd of overschreven.

## Installatie wanneer pull nog kapot is

Merge eerst de PR. Gebruik daarna de al werkende algemene Git-commando's.
Voer elk commando afzonderlijk uit en stop bij een fout:

```bash
cd /volume1/docker/nas-stack
core git status --short
core git fetch origin main
core git merge --ff-only origin/main
core git status --short
```

Dit haalt de reparatie op zonder de oude pull-wrapper te gebruiken. Een
containerrebuild is niet nodig. Er wordt geen reset, clean of geforceerde merge
gebruikt. Git weigert de merge als lokale wijzigingen zouden worden overschreven.

Op de NAS is core/runtime/capacity.py lokaal gewijzigd. Behoud dat werk.
De normale pull-wrapper weigert bewust zolang bijgehouden wijzigingen aanwezig
zijn. Als uitsluitend deze wijziging nog openstaat, kun je haar tijdelijk apart
bewaren en daarna terugzetten (stop bij iedere fout):

```bash
core git stash push -m "Bewaar lokale capacity-aanpassing voor pull" -- core/runtime/capacity.py
core git pull --skip-docs
core git stash pop
core git status --short
```

Bij een conflict blijven de wijzigingen in de stash; los het conflict op voordat
je verdergaat. Zodra de wijziging is teruggezet, weigert een volgende normale
pull opnieuw totdat je haar commit of tijdelijk apart bewaart. Dat is een
beveiliging van gebruikerswerk, geen verbindingsfout.

## Validatie

Regressietests voeren de shell-wrappers uit met een nep-Docker. Ze controleren
SSH/gebruikerconfiguratie voor pull, status/diff/commit/branch/push, argumenten met
spaties, fetchfouten, lokale wijzigingen, .env-behoud en documentatieopties.
Een echte alleen-lezen ls-remote met de gedeelde helper op de NAS controleert
de GitHub SSH-verbinding. Geen productie-pull of deployment uitgevoerd.
