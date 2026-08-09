# SCRUM-78 Databasegroei en contractgrenzen

## Doel en grens

Deze eerste stap meet de acceptatiedatabase read-only. Er worden nog geen
tabellen, kolommen, indexen of records gewijzigd. Het doel is onderscheid maken
tussen echte groei, bewuste audit-/provenancedata en schijnbare overlap tussen
operationele en afgeleide tabellen.

De nulmeting is uitgevoerd op 9 augustus 2026 tegen `nasdb_test`. Herhaal met:

```sh
docker exec -i postgres psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test \
  < database/assessment/scrum78_database_growth.sql
```

## Nulmeting

| Onderdeel | Rijen | Totale omvang | Beoordeling |
|---|---:|---:|---|
| Database | - | 386 MB | Klein; geen capaciteitsprobleem |
| `files` | 237.688 | 284 MB | Grootste operationele tabel |
| `metadata` | 237.673 | 66 MB | Eén technische metadata-state per bestand |
| `file_events` | 37.790 | 15 MB | Append-only audit; nog klein |
| `folders` | 14.144 | 8,0 MB | Normale operationele index |
| Contentgroepen + leden | 6.154 | 2,9 MB | Kleine integriteitslaag |
| Semantic tabellen samen | 718 | circa 1,0 MB | Herbouwbaar en momenteel zeer klein |
| Classification runs/proposals/reviews | 7 | 160 kB | Geen relevante groeidriver |

De nieuwe semantic- en classificationopslag veroorzaakt dus niet de huidige
databaseomvang. `files` en `metadata` gebruiken samen ongeveer 350 MB en zijn de
eerste plaats om index- en datacontracten te beoordelen.

### Bestandsdekking

- Actief: 227.065 bestanden.
- Logisch verwijderd: 10.623 bestanden.
- Actief en leeg: 671 bestanden.
- Actief zonder volledige SHA-256: 223.243 bestanden.

De ontbrekende volledige hashes zijn in de huidige documentgerichte pilot geen
fout: CORE vult SHA-256 gericht aan voor toegestane documenten. Een volume-brede
hashbackfill voor media en systeembestanden valt buiten het persoonlijke
document-MVP en zou onnodige NAS-belasting veroorzaken.

### Events en scans

`file_events` bevat hoofdzakelijk 12.323 `CREATED`, 11.504 `DELETED` en 11.095
`MODIFIED` events. De tabel is auditwaardig en slechts 15 MB. Er is nog geen
aanleiding voor verwijdering of partitionering. Wel moet een periodieke meting
zichtbaar maken of reguliere dagelijkse groei afwijkt van de initiële ingest.

`scan_sessions` bevat 1.055 records: 912 interval-, 131 full- en 12 historische
watchersessies. Met 320 kB is deze historie niet relevant voor ruimtebesparing.

## Datacontracten

| Laag | Tabellen | Contract | Retentie-uitgangspunt |
|---|---|---|---|
| Operationele waarheid | `files`, `folders`, `metadata` | Actuele technische toestand | Behouden zolang bestand/audit nodig is |
| Inhoudsintegriteit | `content_groups`, `content_group_members` | Exacte inhoudsgelijkheid en golden record | Herberekenbaar, maar operationeel belangrijk |
| Operationele audit | `file_events`, `scan_sessions` | Waargenomen mutaties en verwerking | Append-only; beleid pas na groeimeting |
| Semantic extractie | `semantic_runs`, `semantic_documents`, `semantic_chunks` | Versieerbare afgeleide technische metadata | Herbouwbaar; pin pilots en retire oude runs later |
| Embeddings | `semantic_embedding_runs`, `semantic_embeddings_acc` | Modelgebonden afgeleide vectoren | Herbouwbaar per model/revisie |
| Classificatievoorstel | `classification_runs`, `classification_proposals` | Machine-/rulesvoorstel met provenance | Behouden zolang review/audit relevant is |
| Menselijk besluit | `classification_reviews` | Append-only beslissing | Niet samenvoegen met machinevoorstel |
| Actuele classificatie | `v_current_file_classification` | Nieuwste geldige geaccepteerde review | View; geen extra kopietabel |

De semantic-, embedding- en classificationtabellen lijken deels op elkaar omdat
alle lagen run-, file- en contentprovenance nodig hebben. Hun lifecycle en
betekenis verschillen. Ze nu samenvoegen zou extraction, modeloutput en menselijke
waarheid door elkaar halen en juist technische schuld creëren.

## Concrete kandidaten

### Kandidaat A — dubbele metadata-index

`metadata.file_id` heeft zowel een unieke index als een extra niet-unieke index:

```text
metadata_file_id_unique  circa 10 MB
idx_metadata_file_id     circa 10 MB
```

De unieke B-tree kan dezelfde `file_id`-lookups ondersteunen. Een meting met
`EXPLAIN (ANALYZE, BUFFERS)` bevestigde dat de lookup een B-tree-index gebruikt.
De twee indexdefinities waren, afgezien van de unieke constraint, gelijk. De
extra index wordt daarom verwijderd door:

```text
database/migrations/20260809_remove_redundant_metadata_file_id_index.sql
```

De migratie gebruikt `DROP INDEX CONCURRENTLY` om normale metadatawrites niet
langdurig te blokkeren en bespaart circa 10 MB. Zij moet daarom zonder expliciete
transactiewrapper worden uitgevoerd. De rollback maakt de index eveneens
concurrent opnieuw aan.

Toepassen op ACC:

```sh
docker exec -i postgres psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test \
  < database/migrations/20260809_remove_redundant_metadata_file_id_index.sql

docker exec -i postgres psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test \
  < database/assessment/scrum78_verify_metadata_file_id_index.sql
```

De post-check moet alleen `metadata_file_id_unique` tonen en de representatieve
lookup moet die index gebruiken. Controleer daarna ook de metadata-workerhealth.

### Kandidaat B — oude inode/mtime-index

`idx_files_inode_mtime` gebruikt circa 14 MB en had 256 geregistreerde scans.
De actuele identity-query zoekt op `(filesystem_device, inode)` en heeft daarvoor
de partiële `files_device_inode_active_idx`. Onderzoek met `EXPLAIN` en tests of
de oude index nog een backward-compatible consument heeft voordat deze wordt
verwijderd.

### Kandidaat C — width/height-index

`idx_metadata_width_height` gebruikt circa 3,6 MB en had drie geregistreerde
scans. Verwijderen is waarschijnlijk laag risico wanneer dashboard- en
mediaqueries geen width/heightfilter vereisen. Media valt buiten het huidige MVP,
maar het bredere CORE-platform kan deze index later nodig hebben; eerst workload
en queryplannen meten.

### Kandidaat D — lege metadata-attributen

`metadata.duration` is voor alle 237.673 records `NULL`; `missing` is overal
`false`. Dit zijn semantische tech-debt-kandidaten, maar kolommen verwijderen
bespaart weinig ruimte. Eerst besluiten of toekomstige media-extractie deze
velden bewust gaat gebruiken. Prioriteit is lager dan dubbele indexen.

## Niet optimaliseren in het MVP

- Geen semantic/classificationtabellen samenvoegen.
- Geen `file_events` verwijderen zonder audit- en retentiebeleid.
- Geen volledige SHA-256-backfill voor media of systeemdata.
- Geen bron- en afgeleide metadata in één brede JSONB-tabel stoppen.
- Geen extra current-state-tabel naast de bestaande view maken.
- Geen `VACUUM FULL` of andere blokkerende ruimteoperatie zonder noodzaak.

## Retirement legacy AI-tabellen

De oorspronkelijke tabellen `embeddings` en `ai_output` bevatten op ACC beide
nul records en hebben geen actieve runtimewriter. De actuele contracten zijn de
versieerbare `semantic_*`, `semantic_embeddings_acc` en `classification_*`
tabellen. De oude tabellen worden daarom verwijderd door:

```text
database/migrations/20260809_remove_legacy_ai_tables.sql
```

De migratie stopt expliciet wanneer een van de tabellen onverwacht records bevat.
Voor het verwijderen wordt `cleanup_all_execute()` vervangen door een versie die
alleen de actuele operationele tabellen opruimt. De legacy assessment- en
duplicate-tools behouden hun bestaande CSV-metrieknamen met waarde nul, zodat
bestaande rapportverwerking niet breekt.

Toepassen en verifiëren op ACC:

```sh
docker exec -i postgres psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test \
  < database/migrations/20260809_remove_legacy_ai_tables.sql

docker exec -i postgres psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test \
  < database/assessment/scrum78_verify_legacy_ai_retirement.sql
```

De twee `remaining_relation`-waarden moeten leeg zijn,
`has_legacy_reference` moet `false` zijn en alle actuele semantic- en
classificationrelaties moeten blijven bestaan. De rollback herstelt de lege
legacytabellen en de eerdere procedure wanneer een oude consument onverwacht
toch nodig blijkt.

## Aanbevolen vervolg

1. Sla deze meting periodiek op om werkelijke dag-/weekgroei vast te stellen.
2. Pas de migratie voor de aantoonbaar dubbele metadata-index toe op ACC en voer
   de meegeleverde post-check uit.
3. Meet `EXPLAIN (ANALYZE, BUFFERS)` voor identity- en width/heightqueries.
4. Beslis daarna afzonderlijk over inode/mtime en width/height-indexen.
5. Definieer runretentie: `pinned`, `current`, `superseded` en `rebuildable` voor
   semantic en embeddings, zonder menselijke reviews te verwijderen.
6. Houd SCRUM-85 gericht op het actieve-document-MVP; database-optimalisatie mag
   het Nederlandse padbeleid en de reviewpilot niet blokkeren.

## Eerste conclusie

De database groeit, maar is met 386 MB nog ruim beheersbaar. De nieuwe AI- en
classificatielagen zijn niet de oorzaak. De beste eerste optimalisatie is geen
herontwerp maar het veilig verwijderen van aantoonbaar redundante indexen en het
inrichten van een herhaalbare groeimeting. De huidige scheiding tussen bronstate,
afgeleide semantic data, machinevoorstellen en menselijke besluiten blijft staan.
