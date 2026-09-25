# Lokale automatische indeling

De knop **Lokaal alle betalingen indelen** start een eindige achtergrondopdracht voor
alle actieve betalingen zonder bevestigd oordeel, over alle rekeningen en perioden.
Ook eerdere automatische indelingen mogen opnieuw worden bekeken. Nieuwe imports na
de start horen bij een volgende opdracht. Je handmatige oordeel, inclusief bewust
leegmaken van een categorie, wordt nooit automatisch vervangen.

1. Hergebruik de bestaande `suggestions.identity`-herkenning en de actuele handmatige
   beoordelingen. OVpay, expliciete merchant-markeringen en voldoende specifieke
   tegenpartij/rekeningcombinaties gebruiken dezelfde regels als soortgelijke betalingen.
2. Tegenstrijdige menselijke voorbeelden blijven zonder nieuwe automatische indeling.
   Transfers vereisen dezelfde bestaande groeps- en tegenrekeningcontrole.
3. Voor overige betalingen krijgt de lokale LLM de actieve categorietaxonomie en maximaal
   drie tekstueel vergelijkbare menselijke voorbeelden. Alleen bestaande categoriecodes
   en geldige hoofd-/subcategoriecombinaties worden geaccepteerd. Onder confidence 0,75
   wordt niets opgeslagen. Deze modelscore is geen gekalibreerde kans op juistheid.
4. Automatische resultaten verschijnen direct in het overzicht, herkenbaar als lokale
   LLM of soortgelijke betaling. Een handmatige wijziging in het bestaande detailvenster
   krijgt voorrang en wordt bij volgende betalingen als voorbeeld meegenomen.

Automatische beoordelingen gebruiken de bestaande append-only `finance_review_events`
met `confirmed=false`. Alleen de expliciet herkenbare Finance-workerresultaten worden
effectief. De view geeft bevestigde oordelen altijd voorrang; een databasetrigger weigert
nieuwe automatische beoordelingen na een bevestigd oordeel. De bestaande brongegevens,
bedragen, bankreferenties en handmatige reviewhistorie blijven intact.

Een opdracht gebruikt de bestaande Finance-queue en worker, met dezelfde capaciteits-,
PostgreSQL- en gecontroleerde-uitvoeringscontrole per betaling. De worker is al zichtbaar
in Pulse en meldt `categorizing`. De UI toont verwerkt/totaal en aantal ingedeeld.
Stoppen bewaart afgeronde resultaten; een lopende LLM-aanroep kan nog aflopen, maar wordt
na het stoppen niet meer gepubliceerd. Na een herstart worden afgeronde items overgeslagen.
Identieke geminimaliseerde vragen worden binnen een opdracht hergebruikt (maximaal 512
in geheugen). Nieuwe menselijke beoordelingen, groepswijzigingen, importstatus of
taxonomiewijzigingen maken deze cache ongeldig.

## Privacy en beperkingen

- Alleen de lokale OpenAI-compatibele endpoint uit `CORE_LLM_ENDPOINT` en het bestaande
  `CORE_LLM_MODEL` worden gebruikt. Defaults: `http://192.168.68.107:11434/v1` en
  `qwen3.6:latest`. De endpoint moet een letterlijk privaat of loopback-IP bevatten.
- Geen externe fallback, DNS-namen, environment-proxy of HTTP-redirects. Verzoeken hebben
  een timeout van 90 seconden; antwoorden zijn begrensd. Geen tools of financiële acties
  in het modelcontract. Invoer is onbetrouwbare transactietekst, geen instructie.
- Geen bedragen, brondocumenten, groepsnamen of eigen rekeninggegevens in de prompt.
  Tegenpartij en omschrijving worden begrensd, IBANs en e-mailadressen afgeschermd en
  cijfers vervangen. Vrije tekst kan nog persoonsgegevens bevatten: deze gaat alleen
  naar je eigen lokale modelserver. Controleer daar je eigen request-/promptlogging.
- Geen prompts of ruwe modelantwoorden in CORE-logs of database; alleen categorie,
  herkomst, modelversie, confidence en auditkoppelingen. Browserdata blijft achter de
  bestaande Finance-ontgrendeling en same-origin-controles.
- Onvoldoende zekerheid leidt tot geen nieuwe indeling. Een eerdere automatische
  categorie blijft dan staan. Het model wordt niet getraind: menselijke voorbeelden
  worden bij iedere opdracht opnieuw uit de actuele historie samengesteld.
- Dit is een batchfunctie, geen permanente automatische verwerking van toekomstige imports.

## Uitrollen op de NAS

Gebruik eerst de centrale-capaciteitswijziging uit PR #214. Deze feature hergebruikt
de bestaande Finance-gate; ze introduceert geen eigen capaciteitsberekening.
Eerdere Finance-migraties tot en met `20260924_add_finance_bank_references.sql`
moeten aanwezig zijn. Merge en uitrol doet de beheerder.

1. In de NAS-shell:

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

2. Bouw, voer de migratie eenmalig uit en vernieuw **dashboard en finance_worker**:

```sh
core_compose build dashboard &&
/usr/local/bin/docker exec -i postgres sh -c \
  'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d nasdb_test' \
  < database/migrations/20260925_add_finance_local_classification.sql &&
core_compose up -d --no-build --no-deps dashboard finance_worker &&
core_compose ps dashboard finance_worker
```

Ga bij een fout niet door. Herhaal een reeds toegepaste migratie niet.
De Finance-worker krijgt dezelfde lokale endpoint/modelconfiguratie als dashboard.
Alleen bouwen is niet voldoende: beide containers moeten vernieuwd worden.

3. Open Finance, Ctrl+F5, ontgrendel en klik **Lokaal alle betalingen indelen**.
   Volg de voortgang boven de filters. Pas een categorie via het bestaande detailvenster
   aan; dat oordeel blijft bij volgende indelingen leidend. Er is geen herimport nodig.

## Rollback en validatie

De forward migration heeft een empty-only rollback onder `database/migrations/rollback/`.
Na een categorisatieopdracht of automatische review weigert rollback om auditgeschiedenis
te wissen. Stop eerst een actieve indeling voordat oude workerimages worden teruggezet.
Behoud het schema na gebruik; een terugkeer naar een andere effectieve view vereist een
afzonderlijke forward-fix, geen verwijdering van reviews.

Tests gebruiken uitsluitend synthetische transacties en gemockte modelantwoorden:
up/down/up, runtime-rollen, automatische indeling, menselijke voorrang, bestaande
merchant-herkenning, correctie tijdens inference, replay, stoppen, privacyredactie,
ongeldige categorieën, onzekerheid en append-only-bescherming. De inhoudelijke kwaliteit
en beschikbaarheid van het geïnstalleerde lokale model zijn geen onderdeel van deze tests.
