# SCRUM-92 Database-backed CORE policies

## Doel

CORE slaat business policies versieerbaar en per OAP-omgeving op in PostgreSQL.
Deploymentconfiguratie, secrets, hostnamen en containerinstellingen blijven buiten
dit register. De eerste policy bestuurt de actieve documentwerkset; de actieve-
documentview is bewust nog niet onderdeel van deze stap.

De omgevingsstraat is:

```text
O — Ontwikkeling → A — Test & Acceptatie → P — Productie
```

Er bestaat geen afzonderlijke permanente T-omgeving. Iedere omgeving heeft uiteindelijk
een eigen database en daarmee een eigen effectieve policyselectie.

## Datamodel

`policy_versions` bevat immutable snapshots. `UPDATE` en `DELETE` worden door een
trigger geblokkeerd. Een beleidswijziging maakt altijd een nieuwe `policy_version`.

Belangrijke provenance:

- stabiele `policy_code`, contract- en policyversie;
- `development`, `acceptance` of `production`;
- gevalideerde JSONB-configuratie en SHA-256-checksum;
- geldigheidsperiode;
- maker, goedkeurder en wijzigingsreden.

`v_current_policies` kiest per policycode en omgeving deterministisch de nieuwste
`active` snapshot waarvan de geldigheidsperiode nu actief is. Historische snapshots
blijven ongewijzigd aanwezig.

## Eerste policy

`project/policies/active-document-workset-v1.json` definieert:

- een venster van negen kalendermaanden;
- PDF, DOCX en XLSX;
- uitsluitend actuele golden records;
- de afgescheiden OneDrive-documentroot;
- embedded bron-modified, bron-created en filesystem-mtime als activiteitssignalen;
- temporal conflicts en ontbrekende golden records als `needs_review`;
- expliciete uitsluiting van CORE first-seen, raw filesystem-atime en birthtime.

De bestaande `active-workset-v1.json` blijft voorlopig de backward-compatible
runtimepolicy van de DOCX/XLSX-pilot. Omschakeling van die runtime volgt pas nadat de
databasepolicy in A is geverifieerd.

## Migratie en seed in A

Maak vooraf een databasebackup. Voer na merge en pull uit:

```sh
docker exec -i postgres psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test \
  < database/migrations/20260810_add_policy_registry.sql
```

Valideer en plan de seed zonder databasewrite:

```sh
core policy seed --environment acceptance --dry-run
```

Pas dezelfde gevalideerde snapshot daarna idempotent toe:

```sh
core policy seed --environment acceptance --apply
```

Herhalen maakt geen duplicaat. Een bestaand ID met afwijkende provenance veroorzaakt
een fout en geen stille overschrijving. Het commando muteert nooit bestanden.

## Verificatie

```sql
SELECT policy_code, environment, contract_version, policy_version,
       configuration_checksum, effective_from
FROM v_current_policies
WHERE policy_code = 'active_document_workset'
  AND environment = 'acceptance';
```

Controleer de negen maanden en documenttypen:

```sql
SELECT configuration ->> 'activity_window_months' AS activity_window_months,
       configuration -> 'extensions' AS extensions,
       configuration ->> 'golden_records_only' AS golden_records_only
FROM v_current_policies
WHERE policy_code = 'active_document_workset'
  AND environment = 'acceptance';
```

## Rollback

```sh
docker exec -i postgres psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test \
  < database/migrations/rollback/20260810_add_policy_registry.sql
```

Rollback verwijdert het policyregister en de current-view. De bestaande JSON-policy
blijft beschikbaar. Er worden geen document-, metadata- of classificatierecords gewijzigd.

## Vervolg

Na A-verificatie volgt afzonderlijk:

1. active-worksetruntime laten lezen uit `v_current_policies`, met gelogde JSON-fallback;
2. daarna `v_active_documents` bouwen zonder hardcoded negenmaandenwaarde;
3. later dezelfde basis gebruiken voor retention, duplicate-cleanup, classificatie,
   runtime-health en archieflifecycle.
