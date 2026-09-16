# SCRUM-118 — Roadmap, stories en acceptatie

Bij [het fundament](scrum-118-finance-foundation.md). Dit is een uitvoerbaar plan; de onderstaande implementatietests zijn nog niet uitgevoerd. Ronde 1 levert documentatie en Jira-planning, geen runtime- of databasewijziging.

## Jira-roadmap

Alle stories hieronder vallen onder [SCRUM-118](https://hugohoogendoorn.atlassian.net/browse/SCRUM-118). Bestaande beschrijvingen zijn behouden en aangevuld met concrete acceptatiecriteria; features SCRUM-119–123 zijn niet gedupliceerd. Nieuwe stories SCRUM-150–155 vullen ontbrekende onderdelen aan. Geen bankbestanden, echte identifiers, paden of inhoud in Jira opgenomen.

| Fase | Story | Oplevering / gate |
| --- | --- | --- |
| 1, eerst | [SCRUM-126](https://hugohoogendoorn.atlassian.net/browse/SCRUM-126) | Schema, domeinscheiding, rollen, forward/down en synthetisch ingestcontract. Geen echte bankdata nodig. |
| 1 | [SCRUM-124](https://hugohoogendoorn.atlassian.net/browse/SCRUM-124) | Account-/transactiecontract en normalisatie-invarianten; bankonafhankelijk en immutable. |
| 1 | [SCRUM-125](https://hugohoogendoorn.atlassian.net/browse/SCRUM-125) | Bronoccurrences, recordlocators, many-to-one bewijs, sterke ID versus niet-unieke duplicatekandidaat. |
| 2 | [SCRUM-150](https://hugohoogendoorn.atlassian.net/browse/SCRUM-150) — nieuw | Eigenaar stelt lokaal formaat vast; geen bankinformatie door ChatGPT. |
| 2 | [SCRUM-151](https://hugohoogendoorn.atlassian.net/browse/SCRUM-151) — nieuw | Bestaande CORE-privacy/policies/retention hergebruiken; ontbrekende autorisatie, sleutelbeheer en consumer-gates aantonen en aanvullen vóór werkelijke ingest. |
| 3 | [SCRUM-127](https://hugohoogendoorn.atlassian.net/browse/SCRUM-127) | Eerste doel: ASN CAMT.053 volgens openbare specificatie; daadwerkelijke lokale profielmatch blijft gate. Zie ASN-aanvulling in het fundament. |
| 3 | [SCRUM-128](https://hugohoogendoorn.atlassian.net/browse/SCRUM-128) | Extractie/normalisatie en controles met synthetische fixtures. |
| 3 | [SCRUM-129](https://hugohoogendoorn.atlassian.net/browse/SCRUM-129) | Atomische import, lifecycle, retry/crash/idempotency-contract. |
| 3 | [SCRUM-152](https://hugohoogendoorn.atlassian.net/browse/SCRUM-152) — nieuw | Append-only reviews, duplicatebesluiten, effectieve projectie en compensatie. |
| 3 | [SCRUM-153](https://hugohoogendoorn.atlassian.net/browse/SCRUM-153) — nieuw | Queue/leases, resource- en executiongate, Pulse-service en geaggregeerde status. |
| 4 | [SCRUM-130](https://hugohoogendoorn.atlassian.net/browse/SCRUM-130) | Deterministische tegenpartijherkenning, richting en eigen transfers. |
| 4 | [SCRUM-131](https://hugohoogendoorn.atlassian.net/browse/SCRUM-131) | Versiegebonden categorieën en handmatige append-only correcties. |
| 4 | [SCRUM-132](https://hugohoogendoorn.atlassian.net/browse/SCRUM-132) | Inactieve regelvoorstellen uit correcties; expliciete activatie. |
| 5 | [SCRUM-133](https://hugohoogendoorn.atlassian.net/browse/SCRUM-133), [134](https://hugohoogendoorn.atlassian.net/browse/SCRUM-134), [135](https://hugohoogendoorn.atlassian.net/browse/SCRUM-135) | Finance Workset, filters/details, bron en Needs Attention. Alleen na fundament-/ingest-/privacygate. |
| 5 | [SCRUM-136](https://hugohoogendoorn.atlassian.net/browse/SCRUM-136), [137](https://hugohoogendoorn.atlassian.net/browse/SCRUM-137), [138](https://hugohoogendoorn.atlassian.net/browse/SCRUM-138) | Overzicht met expliciete partial/unresolved-status, valuta en transfersemantiek. |
| 6 | [SCRUM-154](https://hugohoogendoorn.atlassian.net/browse/SCRUM-154) — nieuw | Aanvullende CSV/PDF/MT940/CAMT-profielen en later read-only Open Banking-contract. |
| 6 | [SCRUM-155](https://hugohoogendoorn.atlassian.net/browse/SCRUM-155) — nieuw | Opt-in AI-voorstellen pas na bewezen privacy/reviewcontract; geen bankinhoud naar ChatGPT. |

## Eerste implementatieronde: SCRUM-126

Doel: aantonen dat schema en contract de financiële invarianten kunnen afdwingen voordat een echte parser, UI of AI bestaat. SCRUM-124/125 leveren de volgende verdieping van normalisatie en duplicate-/traceabilitylogica; het schema moet die relaties nu al ondersteunen.

Voorgestelde bestanden voor een volgende PR:

- `database/migrations/<date>_add_finance_foundation.sql` en bijbehorende `rollback/`.
- `core/finance/contracts.py` met bankonafhankelijk, versiegebonden input-/outputcontract en pure validators.
- `tests/integration/finance-foundation/` met geïsoleerde PostgreSQL 16 en uitsluitend synthetische fixtures.
- `tests/test_finance_contracts.py` voor parsingvrije contractinvarianten.
- Aanvulling op deze documentatie met werkelijk testbewijs en deployment-/rollbackprocedure.

Geen productiegegevens kopiëren naar testomgeving. Geen migratie uitvoeren in gedeelde `nasdb_test` tijdens ontwikkeling. Eerst isolated up/down/up, constraints en rollen bewijzen, daarna PR en gecontroleerde deployment. Runtime-rollen zijn geen eigenaar en hebben geen DDL-rechten. Geen dashboard-/AI-laag aan deze ronde toevoegen.

## Acceptatiematrix voor het fundament en de vervolgstories

| ID / eigenaar | Synthetisch scenario | Vereiste uitkomst |
| --- | --- | --- |
| F01 / 126 | Lege DB met minimale CORE-tabellen; forward, down, forward | Zelfde schema-invarianten, geen veranderingen aan CORE-brontabellen. |
| F02 / 126 | Rollback bij aanwezige Finance-bronnen/events | Fout zonder dataverlies; service-disable/forward-fix als niet-destructief herstel. |
| F03 / 126 | Workerrol probeert UPDATE, DELETE, TRUNCATE op bankfeiten/events | Database weigert alle drie; legitieme INSERT alleen via contract. |
| F04 / 126 | FK naar ontbrekende file, verkeerde scope of verkeerde contentgroep | Commit geweigerd; geen dangling of kruisende herkomst. |
| F05 / 126 | Transactie zonder bronlink of inconsistent record/source/batch | Deferred constraint weigert commit. |
| F06 / 124 | Decimal, negatieve waarde, valuta, leap day, NULL/lege bronwaarde | Exacte waarden; invalide input afgewezen; geen float of stille rounding. |
| I01 / 125,129 | Zelfde bytes, andere naam/CORE-file-ID, parallel aangeboden | Eén source-content en batch; alle aangeboden CORE-occurrences traceerbaar. |
| I02 / 125,129 | Zelfde requestkey met andere payload | Expliciet conflict; niets stil genegeerd. |
| I03 / 125 | Betrouwbare bank-ID, dezelfde feiten in overlappende exports | Eén transactie met meerdere bronlinks; namespace/account scope gerespecteerd. |
| I04 / 125,129 | Dezelfde bank-ID, ander bedrag/valuta/datum | Conflict zonder bronfeitoverschrijving; batch atomair of volgens bewezen partialbeleid. |
| I05 / 125 | Twee identieke betalingen zonder ID in één bron | Twee locators en twee bankfeiten; fingerprint niet UNIQUE. |
| I06 / 125,152 | Identieke kandidaat in tweede gedeeltelijk overlappende export, geen ID | Unresolved importrecord; geen dubbele gepubliceerde totalen of stille merge. Review same/distinct bepaalt uitkomst. |
| I07 / 125,129 | Replay en parserupgrade van dezelfde bronlocator | Geen nieuw economisch feit; gewijzigde interpretatie als correctie/conflict auditeren. |
| I08 / 129,153 | Crash vóór commit, na commit vóór ack, lease verlopen | Geen half gepubliceerd feit; retry retourneert bestaande uitkomst; stale lease kan niet committen. |
| L01 / 129 | Onbekend profiel, corrupte header, source-changed | Rejected, nul gepubliceerde transacties, foutcode zonder inhoud. |
| L02 / 129 | Eén foutieve rij; bestandstotalen inconsistent | Geen partial als totalen falen; atomaire afwijzing. |
| L03 / 129 | Profiel staat partial toe; onafhankelijke ambigue rij | Correcte tellingen, volledige recordaudit en zichtbare incomplete status; resume herhaalt geen commit. |
| L04 / 152 | Compenseer batch A terwijl B hetzelfde feit onderbouwt | Feit blijft zichtbaar via B; alle A-events blijven bestaan. |
| L05 / 152 | Compenseer laatste bronbatch; replay oude request | Feit niet meer effectief; replay reactiveert niets. Nieuwe revision expliciet nodig. |
| R01 / 152 | Gelijktijdige correcties op zelfde voorganger | Eén winnaar, expliciet conflict voor stale expected_previous; historie intact. |
| P01 / 151 | Verkeerde rol/scope vraagt detail, zoekresultaat of CORE-bestand | Geen toegang, ook buiten de UI; geen lek via cache/error. |
| P02 / 151,153 | Synthetische geheime sentinel in bankvelden/exception | Afwezig in logs, Pulse, Redis, telemetry en generieke exports. |
| P03 / 151 | Finance-document bereikt generieke AI/OCR of cleanup | Geblokkeerd vóór inhoudslezing/verwijdering; lokale privacylabel alleen is onvoldoende. |
| P04 / 151 | Sleutelrotatie en back-uprestore met bestaande identities | Geen nieuwe accounts/duplicaten; oude lookup werkt gedurende gecontroleerde overgang; keys apart hersteld. |
| W01 / 153 | Hoge CPU/geheugen-/DB-/I/O-druk of ontbrekende metrics | Geen nieuwe claim; heartbeat toont reasoncode, resume pas na gezonde hysterese. |
| W02 / 153 | Gecontroleerde uitvoering start tijdens claim | Gemeenschappelijke reservering voorkomt concurrente start; begrensd checkpoint en voorrang. |
| W03 / 153 | Redisrestart/Pulse GET/dead worker | Geen verdwenen DB-jobs of nieuwe import door GET; stale heartbeat zichtbaar, recovery fenced. |
| A01 / 127,128,154 | Multiline CSV, XML XXE, groot bestand/PDF, MT940/CAMT-profielvariant | Begrensde deterministische parser, geen netwerk, unsupported/unsafe input weigert, locators reproduceerbaar. |

Releasegate vóór UI/AI: alle relevante F/I/L/P-scenario's slagen; voor unattended ingest ook W. Tests moeten gedrag tegen echte PostgreSQL controleren, niet uitsluitend aanwezigheid van SQL-strings. Testoutput bevat alleen synthetische waarden en codes. De eigenaar hoeft voor geen van deze tests een bankbestand aan te leveren.

## Ronde 1: daadwerkelijk uitgevoerd

- Volledige epic en bestaande kinderen gelezen; bestaande document-, review-, event-, worker- en Pulse-architectuur geïnspecteerd.
- Read-only databasecatalogus en beperkte, geaggregeerde metadata gecontroleerd; bestandsbeschikbaarheid met stat, zonder inhoud. Na privacyvoorkeur verdere broninspectie gestopt.
- Ontwerp met relaties/constraints, duplicatebeleid, lifecycle, privacyrisico's, roadmap en testmatrix vastgelegd.
- Nieuwe Jira-stories SCRUM-150–155 aangemaakt; SCRUM-124–138 geconcretiseerd met behoud van bestaande tekst.
- Jira-blockerrelaties vastgelegd voor schema, bron-/privacygate, ingest, reviews en latere UI/AI. Bestaande CORE-privacyketen en policyregister expliciet als hergebruikbasis opgenomen.
- Afzonderlijke `codex/scrum-118-finance-foundation` worktree gebruikt; bestaande NAS-checkout en ongetrackte gebruikersbestanden niet bewerkt.

Niet uitgevoerd: bankparsing, bankinhoud lezen, live migraties, implementatietests, workeractivatie, dashboard, AI of deployment. Het exacte ASN-exportprofiel blijft bewust een lokale vervolggate.
