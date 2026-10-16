# Informatief overzicht van automatische indelingen

Open Finance en kies Resultaten bekijken bij Automatische indeling. Kies een
ronde (de laatste 50 staan in de keuzelijst) en bron: CORE-regels plus jouw
voorbeelden, alle automatische indelingen, of lokale LLM.

Per betaling zie je boekdatum, bedrag, CORE-rekeninglabel, tegenpartij,
bankomschrijving, oude categorie, de categorie die in die ronde is toegewezen,
de huidige categorie en herkenningsreden. De lijst onderscheidt nieuw ingedeeld,
verfijnd en gewijzigd. Latere beoordelingen en teruggedraaide bronbijdragen zijn
expliciet herkenbaar. Dit is historie van opgeslagen resultaten, geen lijst van
nog te accorderen voorstellen. Bedragen worden niet uit JSON-floats gereconstrueerd.

Er zijn 50 resultaten per pagina; het totaal geldt voor de hele gekozen ronde en
bron. Nieuwe rondes mogen al worden bekeken terwijl ze lopen; gebruik Resultaten
vernieuwen om de lijst bij te werken. De bestaande overzichtsfilters beperken
deze lijst niet: hij omvat alle rekeningen en perioden van de gekozen ronde.

Bekijk / beoordeel opent de bestaande transactiedetails met actuele gegevens,
bronbewijs en reviewhistorie. Opslaan gebruikt de bestaande eigenaarbeveiliging
en optimistic locking. Daarna wordt het resultaat opnieuw opgehaald. Historische
toewijzingen blijven behouden; een boeking die niet meer actief is heeft geen
bewerkknop.

De alleen-lezen API /api/v1/finance/categorization-results vereist de bestaande
owner-sessie. Geen nieuwe tabellen, migratie, privileges, LLM-aanroepen of logs
met financiële inhoud. Omschrijvingen/rekeninglabels blijven versleuteld in de
database en worden alleen in de beveiligde API ontsleuteld. De lijst en verzoek-
status worden gewist bij sluiten/vergrendelen; late antwoorden worden genegeerd.

## NAS-uitrol

Merge de PR. Met de eerdere Finance-CLI-PR (codex/finance-deploy-cli) gemerged:

```bash
cd /volume1/docker/nas-stack
core git pull --skip-docs
core finance deploy
core finance status
```

Geen migratie nodig. Stop bij fouten en behoud lokale wijzigingen; geen
reset/clean. Na deployment Ctrl+F5. Open Resultaten bekijken, kies een ronde,
controleer bronfilter en paginering, en open een betaling om te beoordelen.
Ook reeds opgeslagen resultaten van oudere rondes zijn beschikbaar; een nieuwe
indelingsronde of XML-herimport is niet nodig.

Tests gebruiken fictieve transacties voor context, verfijning, bronnen, pagina's,
latere correcties, importrollback, owner-only toegang, ontsmette HTML en
verouderde verzoeken. Bestaande refresh/filter/LLM-UI-tests blijven gelden.
Geen productie-bankgegevens gelezen of deployment uitgevoerd.
