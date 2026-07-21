# SCRUM-53 Database Schema Review

Status: removal migration prepared after successful deprecation cycle

Measured: 2026-07-21

Database: `nasdb_test`

## Decision summary

The duplicate hash and MIME columns completed their deprecation cycle. A verified backup exists and a removal plus rollback migration is prepared. Other candidates remain review-only.

| Object | Classification | Evidence | Required next step |
|---|---|---|---|
| `files.xxhash` | Deprecate | Equals `files.hash_path` for 221,451 rows; the worker writes the same path hash to both columns | Stop writes, move index consumers to `hash_path`, monitor, then propose removal |
| `metadata.duration` | Deprecate | NULL for all 225,287 metadata rows; worker explicitly inserts NULL and never updates it | Decide whether media duration is roadmap scope; otherwise stop exposing and later remove |
| `metadata.mime_type` | Deprecate | Duplicates `files.mime_type`; active integrity and cleanup tools already use the file column | Stop metadata writes, observe compatibility, then remove its index and column |
| `ai_output` | Keep pending roadmap decision | Zero rows and no runtime writer; FK to `files` | Confirm AI roadmap before table-level deprecation |
| `embeddings` | Keep pending roadmap decision | Zero rows and no runtime writer; FK to `files` | Confirm semantic-search roadmap before table-level deprecation |

## Live evidence

The live database contains approximately:

- `files`: 225,302 rows
- `folders`: 12,570 rows
- `metadata`: 225,287 rows
- `scan_sessions`: 27 rows at measurement time
- `ai_output`: 0 rows
- `embeddings`: 0 rows

PostgreSQL statistics show active inserts and updates for `files`, `folders`, `metadata` and `scan_sessions`. The AI tables have no recorded writes.

### Hash fields

`metadata_worker.py` calculates:

- `hash_path` as xxHash64 of the normalized path;
- `hash_content` as xxHash64 of the first 1,024 file bytes;
- legacy `xxhash` from the same `hash_path` value.

Live results:

- 225,302 file rows total;
- 221,451 rows where `xxhash IS NOT DISTINCT FROM hash_path`;
- 3,852 rows without `hash_path`, corresponding to legacy/incomplete records;
- `idx_files_xxhash` depends on `files.xxhash`;
- `v_file_integrity` and cleanup diagnostics depend on `hash_path` and `hash_content`.

Decision: retain `hash_path` and `hash_content`; remove the physical `xxhash` column and its index. `v_test_documents` preserves its legacy output name by exposing `hash_path AS xxhash`.

### MIME fields

Both `files.mime_type` and `metadata.mime_type` are written from the same MIME detection result. `metadata.mime_type` has no nulls; `files.mime_type` has 3,852 null rows. There are 3,855 cross-table disagreements. The metadata MIME column is indexed by `idx_metadata_mime_type`; the file MIME column is used by `v_file_integrity`.

Decision: use `files.mime_type` as the canonical value because active integrity, audit and cleanup tooling already depends on it. Remove `metadata.mime_type` and `idx_metadata_mime_type` after the completed compatibility cycle.

### Duration and missing metadata

`metadata.duration` is NULL for all 225,287 rows. The worker always inserts NULL and has no duration extraction path. `metadata.missing` is false for every row and is actively written by the worker.

Recommendation: deprecate `duration` unless media-duration extraction is explicitly planned. Keep `missing` because it is part of active worker semantics even though current values lack variation.

### Paths and identity

`files.path` is the active unique application identity and is used by worker upserts, deletes, rename detection and integrity reporting. `folders.path` plus `files.filename` overlaps structurally with the full path, but 3,851 legacy rows cannot currently be reconstructed consistently because their file path is absent.

Recommendation: keep `files.path`, `folder_id`, `filename` and `folders.path`. Any normalization change would affect unique constraints, rename logic, foreign keys and reports and is outside a column-cleanup migration.

### Timestamps

- `files.created_at`: row creation time; used by historical views.
- `files.updated_at`: current application activity; used by `v_files_last_hour`.
- `files.modified_at_fs`: filesystem mtime; used with inode and size for rename identity.
- `files.deleted_at`: soft-delete marker; used by worker and integrity reporting.
- `files.last_mutation_at`: new mutation classification timestamp; only populated after its migration.

These timestamps describe different events and should be kept.

## Dependency impact

| Candidate | Runtime writer | Index/constraint | View/report | Migration risk |
|---|---|---|---|---|
| `files.xxhash` | `metadata_worker.py` | `idx_files_xxhash` | Legacy/generated schema docs | Medium |
| `metadata.duration` | Worker writes NULL | None | Generated schema docs | Low after deprecation |
| `metadata.mime_type` | Deprecated in `metadata_worker.py` | `idx_metadata_mime_type` | Generated schema docs | Medium |
| `ai_output` | None | PK, FK to `files` | Schema docs | Roadmap-dependent |
| `embeddings` | None | PK, FK to `files` | Schema docs | Roadmap-dependent |

## Controlled follow-up plan

1. Approve or reject each candidate separately.
2. Create a database backup before any schema migration.
3. Deprecate application writes before dropping a populated column.
4. Deploy and observe at least one complete scanner/worker cycle.
5. Run integrity and null/disagreement queries again.
6. Prepare a reversible migration and explicit rollback SQL.
7. Refresh `database/schema/schema.sql` and generated database documentation only after approval.

## Reproducing the assessment

Run the read-only query set on the NAS:

```bash
cd /volume1/docker/nas-stack
/usr/local/bin/docker exec -i postgres psql -U hugo -d nasdb_test \
  < database/assessment/schema_review.sql
```

The query set contains SELECT statements only and does not alter persistent or temporary database objects.
