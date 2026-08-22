# SCRUM-104 — Gecontroleerde duplicate-cleanup-pilot

## Doel

CORE kan overtollige exacte kopieën uit een volledig beoordeelde duplicaatgroep
gecontroleerd naar één technisch quarantainegebied verplaatsen. Dit is een
herstelbare tussenstap en geen fysieke verwijdering.

Het enige doelgebied is:

```text
/volume1/data/.core/quarantaine/duplicaten
```

De leidende kopie blijft op haar bestaande locatie staan. De executor ondersteunt
geen purge- of deletecommando.

## Veiligheidsflow

```mermaid
flowchart LR
    A[Menselijk beoordeelde exacte duplicaten] --> B[Read-only plan]
    B --> C{Alle controles geldig?}
    C -->|nee| D[Geblokkeerd met reason-code]
    C -->|ja| E[Onveranderlijk plan]
    E --> F[Expliciete goedkeuring]
    F --> G[Move naar quarantaine]
    G --> H[Hash en mtime verifiëren]
    H --> I[MOVED-event koppelen]
    I --> J[Herstelbaar via rollback]
```

## Toelatingsvoorwaarden

Een kopie komt alleen in aanmerking wanneer:

- SCRUM-110 een actuele menselijke leidende kopie heeft;
- `v_exact_duplicate_review_handoff` de overdracht expliciet toestaat;
- leidende en overtollige kopie nog bestaan en dezelfde SHA-256 en grootte hebben;
- beide kopieën binnen `/volume1/data` staan;
- de overtollige kopie nog niet in quarantaine of een actief cleanupplan zit;
- het quarantainepad vrij is;
- bron en doel op hetzelfde filesystem staan.

Backupkopieën buiten `/volume1/data` blijven in deze pilot buiten scope.

## Uitvoering

Pas eerst de migratie toe:

```bash
docker exec -i postgres psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test \
  < database/migrations/20260822_add_duplicate_cleanup_executor.sql
```

Begin altijd read-only:

```bash
core cleanup duplicates plan --limit 10 --dry-run
```

Maak pas na controle een onveranderlijk plan:

```bash
core cleanup duplicates plan --limit 10 --create-plan
core cleanup duplicates approve PLAN_ID --confirm PLAN_ID
core cleanup duplicates execute PLAN_ID --confirm PLAN_ID
core cleanup duplicates reconcile PLAN_ID
```

Herstellen naar de oorspronkelijke bronlocatie:

```bash
core cleanup duplicates rollback PLAN_ID --confirm PLAN_ID
```

## Audit en herstel

Plannen, items en statusovergangen zijn append-only. Per item bewaart CORE onder
andere de review-ID, contentgroep, beide file-ID's, SHA-256, grootte, oorspronkelijke
paden, quarantainepad, mtime, policyversie en actor. De watcher registreert de move;
reconciliation koppelt bij voorkeur dit `MOVED`-event aan de CORE-operatie zonder het
document als actief te kwalificeren. Omdat `.core/quarantaine` buiten de normale
inventaris valt, kan de watcher uitsluitend een effectief `DELETED`-event op het
bronpad registreren. CORE accepteert dat alleen als fallback wanneer hetzelfde
planitem al append-only als `verified` is vastgelegd met exact dezelfde SHA-256,
bron en quarantainebestemming. De ruwe gebeurtenis blijft ongewijzigd, fysieke purge
blijft uit en herhaald reconciliëren maakt door de idempotency key geen dubbel bewijs.

### Verwijderingen verklaren

De read-only view `v_file_removal_audit` combineert effectieve `DELETED`-events met
append-only bewijs uit de duplicate-cleanup- en persoonlijke migratie-executors.
Een bewezen quarantaineverplaatsing krijgt `removal_origin = core_quarantine` en
toont onder meer doelpad, geverifieerde SHA-256, actor en herstelbaarheid. Een event
zonder bewezen CORE-operatie blijft `external_or_unattributed`: CORE noemt dit niet
automatisch handmatig, omdat ook OneDrive, SMB, scripts of andere toepassingen de
verwijdering kunnen hebben veroorzaakt.

```sql
SELECT file_id, removed_path, removal_origin, operation_target_path,
       verified_sha256, recovery_available, audit_status, observed_at
FROM public.v_file_removal_audit
ORDER BY observed_at DESC;
```

## Buiten scope

- fysieke verwijdering of purge;
- compressie;
- cleanup van bestanden buiten `/volume1/data`;
- near-duplicates;
- automatisch kiezen of wijzigen van het golden record;
- wijziging van classificatie, lifecycle of doelpad;
- cleanup van een groep waarvan alle kopieën weg mogen.
