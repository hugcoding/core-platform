# Terugkerend: reviewcontext en classificatie-evidence

## Hergebruik en oorzaak

| Functie | Bestaand onderdeel | Uitbreiding |
|---|---|---|
| Categorie/subcategorie en selectie | Finance detail/bulkselectors en taxonomie | Zelfde flow, herstelcallback na opslaan |
| Actieve review | loadRecurring/loadRecurringMembers | Patroon-ID, betaalpagina, scroll/focus en expliciete soortkeuze bewaren |
| Soortadvies | recurring.patterns + bestaande detectie/classificatieprojectie | Read-time proposed_type, geen writes |
| Bevestigen | Bestaande recurring review en classificatie-events | Ongewijzigd, aparte besluiten |

De bulk-savecallback riep loadRecurring zonder context aan. Daardoor verdween de
opengeklapte betaalreview bij het opnieuw renderen. Individuele classificatie vernieuwde
alleen het hoofdscherm. Beide paden herstellen nu dezelfde recurring context; nieuwe
categorie/subcategorie en typeadvies zijn direct zichtbaar. Selectie wordt na succesvol
opslaan gewist; deselecteren blijft uitsluitend uitsluiten van de bulkactie.

## Evidence

De daadwerkelijke taxonomiecode `abonnementen` (waaronder `abonnementen_telefoon` en
`abonnementen_streaming`) ondersteunt subscription als alle aanwezige BEVESTIGDE
classificaties in die hoofdcategorie vallen en EXPENSE zijn. Onbevestigde voorstellen
tellen niet mee. Een bevestigde andere categorie, inclusief `boodschappen`, of TRANSFER
blokkeert deze promotie. TELE2 of andere merchants worden niet hardcoded.

Daarbij vereist het advies: debit, actief enkelvoudig monthly patroon, minimaal drie
observaties, bestaande confidence >= .75, maximaal een gemiste periode/timingoutlier
en robuuste bedragvariatie <= .35. Bestaande detector bewaakt de cycli; geen nieuwe
merchant-normalisatie of detectie. Handmatige groepen krijgen geen nieuwe promotie
op basis van alleen de koppeling. De opgeslagen detectieconfidence wordt niet aangepast.

`proposed_type` is advies. Bestaand reviewed_type en expliciete UI-soortkeuze gaan voor.
Geen automatische recurring bevestiging na classificatie en geen classificatiebevestiging
na recurring review. Geen nieuw schema of migratie.

## Validatie en grenzen

Gerichte pure evidence-test, bestaande Finance-integratietests plus state-separatie en
read-time advies, bestaande selectie/bulk/UI-tests en nieuwe contexttest.
Geen productiegegevens, deploy of merge. Visuele browseracceptatie blijft bij eigenaar.
Geen forecast, boodschappenclusters of uitgebreide detectie. Vervolgcontext: SCRUM-160
/SCRUM-161; geen nieuw Jira-item aangemaakt in deze kleine slice.

## NAS na menselijke merge

Eerdere Finance-migraties, inclusief 20261001 links, blijven vereist. Geen nieuwe migratie.
Voer uit op main, behoud lokale wijzigingen en stop bij fouten:

```sh
cd /volume1/docker/nas-stack
core git status --short
core git branch --show-current
# Indien nodig: core git switch main
core git fetch origin main
core git merge --ff-only origin/main
docker compose -p nas --env-file .env -f docker-compose.yml --profile finance build dashboard
docker compose -p nas --env-file .env -f docker-compose.yml --profile finance up -d --no-deps --force-recreate dashboard
core doctor --finance --worker
```

Fetch/merge vermijdt de bekende aparte core git pull SSH/UID-fout. Die wrapper-fix is
geen onderdeel van deze slice. Geen .env, secrets, worker-rebuild of herimport nodig.
Ctrl+F5, ontgrendelen, Terugkerend openen. Open een maandelijks patroon en betalingen,
selecteer een subset, kies Abonnementen/Telefoon (of Streaming) en sla op. Dezelfde
review/betaalpagina blijft beschikbaar, nieuwe classificatie zichtbaar, patroon blijft
proposed. Controleer passend subscription-advies, corrigeer Soort en bevestig daarna
apart. Niet-geselecteerde betalingen blijven ongewijzigd. Controleer tevens dat
Boodschappen en transfers geen subscription-advies krijgen. Deel geen bankdata.
