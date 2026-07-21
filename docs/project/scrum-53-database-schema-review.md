# SCRUM-53 Database Schema Review

Status: read-only assessment  
Gemeten: 21 juli 2026  
Database: `nasdb_test`

De volledige repositorybron staat in `project/reports/SCRUM-53-database-schema-review.md`. Deze pagina ontsluit de beslissingen en meetresultaten in MkDocs.

## Beslissingen

In de eerste fase worden geen kolommen verwijderd. De worker stopt eerst met schrijven naar dubbele velden; fysieke verwijdering volgt alleen na backup, observatie en een afzonderlijk goedgekeurde migratie.

| Object | Classificatie | Bewijs | Vervolgactie |
|---|---|---|---|
| `files.xxhash` | Deprecate | Dupliceert voor 221.451 rijen `files.hash_path` | Writes stoppen, indexgebruik controleren en later verwijderen |
| `metadata.mime_type` | Deprecate | Dupliceert het actief gebruikte `files.mime_type` | Writes stoppen, observeren en later index plus kolom verwijderen |
| `metadata.duration` | Deprecate-kandidaat | Alle 225.287 waarden zijn `NULL` | Eerst besluit over media-duration-roadmap |
| `files.last_mutation_at` | Deprecate | Alle 2.222 gevulde waarden waren gelijk aan `updated_at`; geen runtime-reader gebruikt het veld | Writes stoppen, volledige cyclus observeren en later verwijderen |
| `ai_output` | Keep pending decision | Geen rijen en geen actieve writer | AI-roadmap bevestigen |
| `embeddings` | Keep pending decision | Geen rijen en geen actieve writer | Semantic-search-roadmap bevestigen |

## Canonieke velden

### Hashes

- `files.hash_path`: xxHash64 van het genormaliseerde pad;
- `files.hash_content`: xxHash64 van de eerste 1.024 bestandsbytes;
- `files.xxhash`: legacy duplicaat van `hash_path`, nu uitgefaseerd.

### MIME

`files.mime_type` blijft canoniek. De integriteitsview, databaseaudit en cleanup-tools gebruiken deze kolom al. `metadata.mime_type` wordt tijdens de compatibiliteitsperiode nog behouden, maar ontvangt geen nieuwe writes meer.

### Mutatietijd

`last_mutation_type` blijft behouden. De metadata-worker bepaalt dit veld bij create, modify, rename, move, restore en delete. Dezelfde worker schreef voor iedere classificatie zowel `updated_at` als `last_mutation_at` met `NOW()`. Omdat geen runtimeconsument `last_mutation_at` leest, is `updated_at` voortaan het canonieke tijdstip van de laatste mutatie.

## Live omvang

- `files`: 225.302 rijen;
- `folders`: 12.570 rijen;
- `metadata`: 225.287 rijen;
- `ai_output`: 0 rijen;
- `embeddings`: 0 rijen.

## Veilig vervolg

1. Maak een databasebackup.
2. Pas de niet-destructieve deprecatiemigratie toe.
3. Deploy de bijgewerkte metadata-worker.
4. Observeer minimaal één volledige scanner/worker-cyclus.
5. Herhaal het read-only assessment.
6. Maak pas daarna een afzonderlijke dropmigratie met rollbackprocedure.

## Assessment uitvoeren

```bash
cd /volume1/docker/nas-stack
/usr/local/bin/docker exec -i postgres psql -U hugo -d nasdb_test \
  < database/assessment/schema_review.sql
```

Dit assessment bevat uitsluitend `SELECT`-statements.
