# Taken voor Hugo — vervolg op SCRUM-160

Slices 1 en 2 staan samen in PR #221; nog niet gedeployed. Merge/pull/deployment
blijven bij Hugo. Voor vervolgslices begin je na merge op actuele main met een
nieuwe codex-branch. Maximaal 50% totaal verbruik van het vijfuurvenster.
Dagelijkse/wekelijkse betalingen vallen buiten recurrence en forecast; algemene
betalingsherkenning/categorisatie mag ze wel blijven gebruiken.

## Taak 1 — Slice 2: Terugkerend-overzicht met auditeerbare patroonreview

**Doel/waarom:** eigenaar kan persisted patronen begrijpen, bevestigen, afwijzen en
inactief zetten; maandelijkse recurrence is niet automatisch een abonnement.
**Status:** afgerond in PR #221. Onderstaande lijst beschrijft de implementatie;
niet opnieuw uitvoeren. **Afhankelijkheid:** beide migraties in de PR.

**Componenten:** `dashboard/static/finance.html`, `finance.js`, `finance.css`,
`dashboard/finance.py`, `core/finance/recurring.py`, `tests/test_finance.py`, bestaande
`showSuggestions`, `updateSuggestionSelection`, `approveCategorySelection` en review/replay helpers.

1. Voeg de weergave Terugkerend aan de bestaande Finance UI toe. Gebruik GET `/recurring`
   met account/paginering en POST `/recurring/detect`; volg bestaande jobstatus en Pulse.
   Toon merchant, accountlabel uit bestaande accountgegevens, cadence, mediane bedragen/range,
   observations, last/next expected, confidence, stale en status.
2. Voeg append-only **pattern**-reviewevents toe (classification-reviewevents zijn per
   transactie en mogen niet voor patroonreview worden misbruikt). FK pattern/detection,
   actor owner, idempotency UUID/digest, predecessor en state confirmed/rejected/inactive.
   Typekeuze subscription/fixed_cost/periodic_transfer/other_recurring vereist owner-review
   of expliciete aanvullende evidence. Forward + empty-only rollback + DB-roltests.
3. Voeg beveiligde review-API toe met bestaande `uid`/`replay`, owner-boundary en
   optimistic concurrency tegen detection-ID + laatste review-ID. Laat de detector nooit
   een menselijke afwijzing overschrijven. Een identieke detectierun heropent niets.
   Begin conservatief: afwijzing blijft tot expliciete heropening; toon nieuwe evidence
   apart. Geen willekeurige automatische reset bij alleen een datum-/versiewijziging.
4. Gebruik `/recurring/{id}/transactions` voor details en bestaande source-links.
   Pattern membership blijft een onveranderlijke detectiesnapshot. UI-selectie is tijdelijk.
5. Bereken classificatiestatus uit actuele bestaande reviews (manual confirmed > automatische
   indeling, onbekend/conflict apart). Bewaar geen tweede classificatiewaarheid op patterns.

**Tests:** proposal tonen, load/error/stale/paging, owner-only/CSRF, review replay, dubbele
request, stale predecessor, rejected blijft rejected bij onveranderde/herhaalde detectie,
nieuwe source-evidence blijft zichtbaar zonder owner-review te wissen, source rollback,
lege/populated rollback en immutable triggers.

**Verificatie:** `python -m unittest discover -s tests -p 'test_finance*.py' -q`; draai
`node tests/test_finance_recurring_ui.cjs`. Bestaande
frontendregressies: `node --test tests/test_finance_selection.cjs tests/test_finance_management.cjs`.
Gebruik de geisoleerde Finance PostgreSQL-teststack uit het foundationdocument.

**NAS na merge:** build dashboard + worker, pas de nieuwe slice-2 migration eenmaal toe
met het psql-commando uit foundation (vervang alleen de migratiebestandsnaam), recreate
beide services, `core doctor --finance --worker`, Ctrl+F5. Review eerst fictieve fixtures
in test; eigenaar valideert productie lokaal zonder bankgegevens te delen.

## Taak 2 — Slice 3: uitsluitend geselecteerde peers via bestaande classificatie

**Doel/waarom:** een terugkerend patroon helpt bij indeling zonder tweede engine en
zonder gedeselecteerde transacties mee te nemen. **Status:** handmatige bulkkeuze met
expliciete IDs is geimplementeerd; automatische classifier/proposal-triggers hieronder
blijven vervolgwerk. Zie finance-recurring.md voor samenvoegen/losmaken en uitrol.
**Afhankelijkheid:** slice 2 stabiel; pattern membership/detection-ID beschikbaar.

**Componenten:** `classification.py` (`conflicts`, `predecessor`, `insert_suggestion`),
`local_classification.py` (`decide`, `step`, `revision`), bestaande categorization targets/results,
`dashboard/finance.py` (`approve_category_selection`, `request_categorization`) en
de bestaande suggestions-checkboxhelpers in `finance.js`/`test_finance_selection.cjs`.

1. Hergebruik de bestaande checkbox/select-all/action-bar logica. Alleen indien nodig
   maak die helper klein parametriseerbaar; geen tweede selectiesysteem. Toon gekozen
   aantal en bied selecteren/deselecteren per item en alles aan. Nul selectie: geen request.
2. Request bevat **expliciete** transaction IDs + detection-ID + idempotency key. Server
   valideert UUIDs, uniekheid, max. batchgrootte conform bestaande 50-grens, actueel membership,
   actieve bronnen en geschiktheid. Buitenlandse/ongeldige IDs weigeren de hele actie.
   Geen defaults die alle leden meenemen, ook niet bij ontbrekende/lege lijst.
3. Breid bestaande categorization-enqueue uit om alleen die IDs in
   `finance_categorization_targets` te zetten. Bestaande open-job-lock/replay en
   targets/results voorkomen dubbele jobs/results. Een gedeselecteerd item krijgt geen
   target, proposal of review en blijft lid van het patroon.
4. Hergebruik bestaande menselijke merchant-peers en `conflicts`; handmatige confirmed
   evidence is leidend. Conflicterende owner-oordelen laten abstainen. Bewaar source_review_id,
   detection/pattern ID en methodeversie bij resultaten/voorstellen. Gebruik reviewevent-FK
   voor auditeerbaarheid; geen kopie van categorieen als nieuwe waarheid.
5. Bewaar eerst **voorstellen** totdat de owner accordeert. De bestaande lokale classifier
   maakt automatisch effectieve, niet-confirmed indelingen; audit dit verschil expliciet
   voordat je hem vanuit recurring aanroept. Indien nodig voeg een gerichte proposal-modus
   toe aan dezelfde pipeline, geen alternatieve classifier. Bescherm huidige owner-prioriteit.
6. Optionele automatische trigger mag alleen als proposal/job via dezelfde pipeline,
   betrouwbaar pattern en expliciete deduplicatiesleutel (detection, transaction,
   classifier-version). Geen recurrente feedback uit auto-proposals: die tellen niet als
   onafhankelijk handmatig bevestigd voorbeeld. Laat de optionele trigger uit tot deze tests groen zijn.

**Tests:** alles/een/meerdere/geen geselecteerd; API verwerkt exact IDs; vreemde/duplicate/stale
IDs; deselecteren is geen reject en wijzigt membership niet; manual peer evidence en conflicts;
geen circulaire evidence; dubbele request/job/proposal; gelijktijdige owner-review wint;
private logs; bestaande classificatie- en selection-regressies.

**Verificatie:** dezelfde Python/DB-tests; `node --test tests/test_finance_selection.cjs
tests/test_finance_local_classification.cjs tests/test_finance_recurring.cjs`.
**Migraties:** alleen aanvullende audit-/idempotencyvelden of proposal-modus als huidige
tabellen tekortschieten; forward/rollback + tests verplicht. **NAS:** beide images rebuild/recreate,
eventuele migratie vooraf, doctor; eigenaar controleert dat een gedeselecteerde betaling ongewijzigd blijft.

## Taak 3 — Slice 4: EXPECTED occurrences uit betrouwbare recurring evidence

**Doel/waarom:** verwacht moment/bedrag tonen zonder echte transacties of saldo te wijzigen.
**Status:** niet gestart; slice 1 bevat alleen `next_expected`, geen forecast.
**Afhankelijkheid:** slices 1–3 stabiel, confirmed/rejected/stale betekenis vastgesteld.

**Componenten:** `recurring.py` (cadence, typical day, month_end, median amount), bestaande
Finance-periodefilters, API/owner-boundary en source/membership-links.

1. Maak een pure kalenderfunctie die current month/next month/3 months/12 months in een
   expliciete as-of periode genereert. Gebruik bestaande cadence + clamping voor maandultimo,
   geen vaste 30/365-dagenoptelling. Bedragen blijven medianen met historisch bereik.
2. Gebruik afzonderlijke EXPECTED response-items; nooit INSERT in finance_transactions,
   import_records of saldoankers. Stabiele occurrence identity = pattern ID + geplande
   period slot; bewaar detection-ID en versie als provenance. Datumcorrectie mag niet
   dezelfde periode dubbel doen verschijnen.
3. Toon ACTUAL en EXPECTED apart. Plan matching via occurrence-ID naar bestaande transaction-ID,
   met state expected/matched/overdue/inactive. Alleen kleine, eenduidige automatische
   reconciliation implementeren; anders expliciet apart vervolg en geen gecombineerde totalen.
   Geen voorspelling en actual samen meetellen. Gemiste betaling stopt geen patroon vanzelf.
4. Owner rejected/inactive en stale evidence niet stil als bevestigde forecast tonen.

**Tests:** alle horizonten, jaargrens/schrikkeljaar, maandultimo, variabele bedragen/outlier,
identieke herhaling, source rollback/stale, expected != actual, geen saldo-/transactiemutaties,
matchingambiguiteit indien matching wordt gebouwd. Pure Python + bestaande DB-regressies;
gerichte frontendtest `node --test tests/test_finance_recurring.cjs`.
**Migraties:** bij afgeleide forecast niet nodig; alleen matching-events persistent indien
nodig, append-only met forward/rollback/tests. **NAS:** rebuild/recreate gewijzigde services,
doctor; vergelijk handmatig een fictief bevestigd patroon met de kalenderverwachting.

## Taak 4 — Slice 5: afgeleide structurele maandlasten

**Doel/waarom:** transparante schatting zonder eigen transfers als kosten te tellen.
**Status:** niet gestart. **Afhankelijkheid:** eerdere slices klaar en dagelijkse usage
betrouwbaar onder de afgesproken grens indien beschikbaar; geen nieuwe slice bij circa 60% daggebruik.

1. Hergebruik actuele patternreviews en bestaande transfer/account/classificatielogica.
   Alleen debit-kosten; sluit interne en bevestigd als TRANSFER ingedeelde boekingen uit.
   `other_recurring` is niet automatisch een structurele kostenpost; toon onzekerheid apart.
2. Pure Decimal-afleiding: weekly * 52 / 12, monthly * 1, quarterly / 3, yearly / 12.
   Vermeld deze jaarweekconventie. Scheid confirmed van proposed/probable, en valuta van elkaar.
   Geen nieuwe saldo-/kostentabel; rond alleen presentatie af.
3. Hergebruik account/groep/periodeselectie en overzichtstijl. Geen dubbele optelling
   van beide kanten van interne transfers, actual en expected, of stale/rejected patronen.

**Tests:** vier cadences, Decimal-afronding, credit uitgesloten, interne transfers en
groepwissel uitgesloten, confirmed/proposed gescheiden, verschillende valuta en staleness.
**Verificatie/NAS:** Python/DB/frontendtests zoals boven, geen migratie bij afgeleide berekening;
dashboard rebuild/recreate en doctor. Leg benodigde vervolgkeuzes in die PR vast.
