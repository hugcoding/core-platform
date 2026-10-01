# Terugkerende betalingen — SCRUM-160

## Oplevergrens

Slices 1 en 2: deterministische detectie, persistente evidence, bestaande worker,
owner-only API en het Terugkerend-overzicht met append-only patroonbeoordelingen.
Handmatig samenvoegen/losmaken en expliciet geselecteerde betalingen categoriseren zijn toegevoegd.
Geen automatische recurring-classificatie, forecast-occurrences of maandlastentotalen.
Vervolgwerk: [Taken voor Hugo](finance-recurring-tasks.md).
Gebruikersgrens: maximaal 50% totaal verbruik van het vijfuurvenster.

## Reuse-map

| Gewenst | Bestaande component | Uitbreiding |
|---|---|---|
| Transacties/rekeningen/bronnen | `finance.v_transactions`, accounts, transaction_sources | Geen nieuw transactie- of rekeningmodel; lidmaatschap verwijst naar bestaande transacties |
| Merchant-normalisatie/identiteit | `core/finance/suggestions.py`: `identity`, `merchant_identity`, `METHOD` | Dezelfde matcher; HMAC-groepssleutel per rekening/identity, geen eigen naamnormalisatie |
| Classificatie en menselijke voorrang | `classification.py`, `local_classification.py`, `v_transactions` | Alleen bestaande inputrevision hergebruikt; geen classificatie als detectievoorwaarde |
| Transfers/groepen | `account_groups.transfer_scope`, `internal_transfer_group` | Bestaande groepsgrens bepaalt `periodic_transfer` |
| Taken/capaciteit/Pulse | `store.enqueue`, `finance_ingest_jobs`, `finance_worker.admitted/gate`, Pulse heartbeat/queue | Nieuwe `job_kind=recurring`, per-account checkpoint; geen tweede queue/worker/notificatiesysteem |
| Confidence/provenance | Numerieke confidence en append-only conventie, encrypt/HMAC | Recurrence-specifieke score/evidence; geen gedeeld nieuw confidence-framework |
| API/privacy | `dashboard/finance.py`, `finance_boundary`, `transaction()` | Endpoints achter bestaande owner/same-origin/no-store grens |
| Review/bulk/selectie | `replay`, `approve_category_selection`, bestaande suggestions-dialog en checkboxhandlers | Nog niet gewijzigd: hergebruiken in slices 2–3 |
| Tests/migraties | `tests/test_finance.py`, bestaande fictieve CAMT-helpers en isolated Compose | Pure detectietests, integratietest, up/down/up en beschermde rollback |

## Detectiecontract

Expliciete detectieopdracht; nooit een volledige analyse bij een GET/page load.
De worker groepeert actieve transacties per rekening, bestaande merchant-identity,
richting en valuta. Classificatie en LLM zijn geen input. Geen bruikbare identity:
geen patroon. Geen vergelijkingen tussen alle transactieparen; sorteren binnen groepen
is O(n log n). Nieuwe lookup-indexen ondersteunen bestaande actieve-bronqueries.

Minimaal drie waarnemingen. Weekly: intervallen van 7 of eenmaal 14 dagen met maximaal
twee dagen intervalafwijking en een consistente weekdag (+/-1). Monthly/quarterly/yearly:
kalendermaanden, dagafwijking maximaal drie dagen, correctie voor maandultimo/schrikkeljaren.
Eén gemiste periode is toegestaan. Vanaf vijf waarnemingen mag één datum buiten de
gebruikelijke dag vallen, mits de periode-intervallen nog passen. Dubbele dagen,
meerdere gemiste perioden en sterk gemengde ritmes worden conservatief overgeslagen.

Typisch bedrag = mediaan; variatie = mediane absolute afwijking / absoluut mediaanbedrag.
Min/max is het werkelijk waargenomen bereik, geen voorspellingsinterval. Eén bedraguitschieter
verandert de mediaan niet direct. Confidence (0–1) combineert observatieaantal, timingfit,
gemiste periode en bedragvariatie; dit is een uitlegbare heuristiek, geen gekalibreerde kans.
`next_expected` is de volgende kalenderdatum na de laatste waarneming, ook als die inmiddels
in het verleden ligt. Ouderdom alleen maakt een patroon niet inactief.

`monthly` wordt nooit vanzelf `subscription`. Zonder aanvullende evidence is het type
`other_recurring`; alleen bestaande interne-transferlogica levert `periodic_transfer`.
Inkomsten blijven credit-patronen. Er wordt nog geen kostentotaal berekend.

## Opslag, replay en grenzen

Migratie `20260930_add_finance_recurring.sql` voegt vier append-only tabellen toe:
patterns (stabiele identity), detections (versioned snapshots), members (FK naar transacties)
en scans (job/account checkpoints + inputrevision). API-rol heeft alleen SELECT op deze
tabellen; ingestrol INSERT. Members kunnen uitsluitend in de creatietransactie aan een
snapshot worden toegevoegd; account/valuta/richting en evidence-aantal worden gecontroleerd.
Naam, bedragen en datumevidence worden met bestaande Finance-sleutels versleuteld.

Een onveranderde revision wordt niet opnieuw geanalyseerd; identieke evidence krijgt geen
extra snapshot. Per account wordt atomair gewerkt en voor elk volgend account controleert
de bestaande worker opnieuw capaciteit. Maximaal 25.000 actieve transacties per account;
overschrijding geeft `recurring_account_scan_limit`, zonder stilzwijgende truncatie.
Een veranderde inputrevision tijdens een accountscan geeft `recurring_inputs_changed`;
start na stabilisatie een nieuwe detectieopdracht. Afgeronde accounts blijven auditeerbaar.

Rollback van een import wijzigt geen patternhistorie. De API verbergt actieve snapshots
met ingetrokken bronnen direct; herdetectie maakt een nieuwe snapshot (eventueel inactive).
Een veranderde bron-/review-/groepsrevision wordt als `stale` getoond totdat opnieuw gescand is.
Deze grove revision kan ook door een categoriewijziging veranderen. Eén identity kan in
deze slice één ritme hebben: meerdere diensten/ritmes bij dezelfde merchant worden niet gesplitst.
De matcher blijft de bestaande matcher: deze slice voegt geen extra bankprofielen toe.

De terugweg onder `database/migrations/rollback/` werkt alleen voor een ongebruikte feature.
Na een recurring job/patroon weigert deze auditgegevens te verwijderen. Behoud na gebruik
het schema; schakel aanvragen uit en herstel zo nodig via een afzonderlijke forward-fix.

## NAS-uitrol na menselijke merge

Voer uit in de NAS-shell. Stop bij een fout; pas een reeds toegepaste migratie niet opnieuw toe.
Geen nieuwe secrets, herimport of wijziging van de veilige Finance-default nodig.

```sh
cd /volume1/docker/nas-stack
core git pull --skip-docs
/usr/local/bin/docker compose --profile finance build dashboard finance_worker
/usr/local/bin/docker exec -i postgres sh -c \
  'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d nasdb_test' \
  < database/migrations/20260930_add_finance_recurring.sql
/usr/local/bin/docker exec -i postgres sh -c \
  'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d nasdb_test' \
  < database/migrations/20260930_add_finance_recurring_reviews.sql
/usr/local/bin/docker compose --profile finance up -d --no-deps --force-recreate dashboard finance_worker
core doctor --finance --worker
```

Open Finance en kies **Terugkerend**. Kies **Opnieuw herkennen** (alle rekeningen),
wacht op de bestaande jobstatus/CORE Pulse en kies **Vernieuwen**. Filter vervolgens
op rekening. Dagelijkse en wekelijkse patronen vallen buiten detector v2, overzicht en toekomstige
forecast. De bestaande algemene betalingsherkenning/classifier blijft ongewijzigd.

Het overzicht toont identiteit, rekening, type, ritme, bedrag/bereik, observaties,
laatste/verwachte datum, heuristische confidence, huidige categorie/subcategorie,
aantallen handmatig bevestigde classificaties en patroonstatus. Betalingen openen
het bestaande detailvenster, met classificatiehistorie en bronlinks.

**Bevestigen**, **Afwijzen**, **Inactief maken** en **Heropenen** voegen een
`finance_recurring_reviews`-event toe. Een herhaald verzoek met dezelfde key is
idempotent; een verouderde detection/review-ID geeft 409. Nieuwe detecties wijzigen
het eigenaarsbesluit niet en krijgen een melding nieuwe evidence. Bij inactieve
detectie toont het overzicht inactive; het laatste eigenaarsoordeel blijft bewaard.
Een categorie wijzigen in het bestaande transactievenster verandert geen patroonreview.
De volgende refresh leest de actuele classificaties uit `v_transactions`.

Geen herimport, nieuwe secrets of handmatige codeaanpassing nodig. Rollback alleen
bij lege featurehistorie: eerst reviews-rollback, dan detectie-rollback. Na gebruik
weigeren de rollbackbestanden auditgeschiedenis te verwijderen; behoud het schema
voor een forward-fix.

## Tests

Lokaal, met de bestaande Finance-testdependencies:

```sh
python -m unittest discover -s tests -p 'test_finance*.py' -q
```

Databasevalidatie uitsluitend in een aparte checkout/testproject, zonder productie-.env of bankmounts:

```sh
docker compose -p core-recurring-test -f tests/integration/finance/compose.yml build integration
docker compose -p core-recurring-test -f tests/integration/finance/compose.yml run --rm integration \
  python -m unittest tests.test_finance tests.test_finance_recurring -q
docker compose -p core-recurring-test -f tests/integration/finance/compose.yml down -v
```

Deze bestaande teststack gebruikt `core_finance_test` in tmpfs, fictieve bankbestanden
en het bestaande `nas-dashboard:latest` image als testbasis. De tests wijzigen geen
productiedatabase of productiecontainers.

## Samenvoegen, prijzen en geselecteerde categorieen (2026-10-01)

Een andere betaalnaam of bedrag mag hetzelfde abonnement vertegenwoordigen. Via
**Samenvoegen onder andere naam** kies je een hoofdpatroon op dezelfde rekening,
met dezelfde richting en valuta. Kandidaten zijn gepagineerd. Omschrijving en perioden
blijven zichtbaar; er is geen automatische fuzzy samenvoeging. Het hoofdpatroon bepaalt
naam, soort en eigenaarstatus. Alle afzonderlijke detecties en reviews blijven intact.
Bestaande groepen kunnen niet onder een andere groep hangen: voeg losse patronen toe
of maak eerst componenten los. **Losmaken** schrijft een nieuw event; niets wordt gewist.

`finance_recurring_links` bewaart owner, predecessor, idempotency-key en FK-relaties.
De membership-view leidt alleen de actuele koppeling af. Triggers/constraints blokkeren
zelfkoppelingen, cycli, kruisrekening/richting/valuta en auditmutaties. Link- en bulk-API
gebruiken bestaande sessie-, same-origin- en idempotencybeveiliging.

Detector v2 houdt maand/kwartaal/jaar en kalenderdatum primair. Bedragvariatie is een
secundaire confidencefactor, geen eis van gelijke bedragen. De laatste waargenomen
bedragstap is `(abs(nieuw)-abs(vorig))/abs(vorig)*100`; dit bewijst geen contractwijziging.
Bij handmatige groepen vergelijkt de indicator de typische bedragen van de componenten
op volgorde van hun laatste betaling. Gaten/overlap blijven per component zichtbaar.
Een gekoppelde groep krijgt bewust geen gecombineerde verwachte datum: de koppeling
bewijst geen doorlopend ritme. Er worden nooit ontbrekende transacties aangemaakt.

**Betalingen en categorieen bekijken** toont max. 50 actieve betalingen per pagina.
Kies categorie/subcategorie en transactietype uit de bestaande taxonomie, vink gewenste
betalingen aan en accordeer. Niets is vooraf aangevinkt. Paginawisseling wist de selectie.
Handmatige beoordelingen zijn standaard uitgesloten; overschrijven vereist expliciete
opt-in plus selectie. Alleen aangeleverde IDs worden in een atomaire transactie verwerkt.
Vreemde/stale/duplicate IDs weigeren de hele batch. Retry hergebruikt de key. Dezelfde
`insert_manual` helper wordt gebruikt door individuele en bulkclassificatie; bestaande
owner-prioriteit en leervoorbeelden blijven leidend. Geen nieuwe classifier of queue.

### Uitrol na menselijke merge

De twee migraties van 20260930 moeten al zijn toegepast. Alleen deze nieuwe migratie
is nodig; stop bij een fout en herhaal geen reeds toegepaste migratie:

```sh
cd /volume1/docker/nas-stack
core git status --short
core git branch --show-current
# Indien nodig eerst: core git switch main
core git pull --skip-docs
docker compose -p nas --env-file .env -f docker-compose.yml --profile finance build dashboard finance_worker
docker exec -i postgres sh -c \
  'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d nasdb_test' \
  < database/migrations/20261001_add_finance_recurring_links.sql
docker compose -p nas --env-file .env -f docker-compose.yml --profile finance up -d --no-deps --force-recreate dashboard finance_worker
core doctor --finance --worker
```

Als `core git pull` nog de bekende SSH/UID-fout heeft, gebruik op main
`core git fetch origin main` gevolgd door `core git merge --ff-only origin/main`.
Geen reset/clean, geen .env/secrets aanpassen, geen herimport.
Ctrl+F5, ontgrendel, **Terugkerend > Opnieuw herkennen** om v2-evidence te maken;
volg bestaande jobstatus/Pulse en vernieuw daarna. Controleer samenvoegen/losmaken,
prijspercentage, categorisatie van een beperkte selectie en behoud van niet-geselecteerde
betalingen. De rollback van deze migratie weigert zodra koppelingen zijn vastgelegd.
Bevestigde classificaties blijven gewone bestaande reviewevents en worden nooit verwijderd.

Tests: `python -m unittest tests.test_finance tests.test_finance_recurring -q` in de
geisoleerde teststack; `node tests/test_finance_selection.cjs`,
`node tests/test_finance_recurring_ui.cjs`, `node tests/test_finance_recurring_bulk.cjs`.
