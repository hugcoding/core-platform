# SCRUM-61 — Read-only classification design

## Objective

CORE keeps a broad inventory of `/volume1` while separately deciding which
files may participate in cleanup, migration to `/volume1/data`, or semantic
processing. Inventory membership never authorizes a physical mutation.

## Safety defaults

- Every unclassified file is `unknown`.
- `unknown` is ineligible for cleanup, migration, and semantic processing.
- System, application, cache, temporary, secret, backup, and archive files
  remain visible but are not action-eligible.
- Personal documents, personal media, and projects are candidates only.
- Candidate classifications require review before migration.
- Classification cannot directly move, overwrite, quarantine, or delete data.
- Physical operations require a separate immutable manifest, dry-run,
  approval, copy verification, audit event, and rollback plan.

## Proposed categories

| Category | Inventory | Cleanup | Migration | Semantic |
|---|---:|---:|---:|---:|
| `unknown` | yes | no | no | no |
| `system` | yes | no | no | no |
| `application_data` | yes | no | no | no |
| `cache_or_temporary` | yes | no | no | no |
| `secret` | yes | no | no | no |
| `backup_or_archive` | yes | review | review | no |
| `personal_document` | yes | review | review | review |
| `personal_media` | yes | review | review | later |
| `project` | yes | review | review | later |

The initial assessment uses candidate categories for documents and media
because an extension alone is not sufficient evidence of ownership or intent.

## Proposed derived model

No migration is part of the first phase. The proposed backward-compatible
table for a later approved phase is:

```text
file_classifications
--------------------
file_id
category
cleanup_scope
migration_scope
semantic_scope
retention_policy
classification_source
rule_id
confidence
review_status
reviewed_by
reviewed_at
reason
classification_version
classified_at
```

The current `files` row remains the inventory source of truth.
Classification is derived policy state and can be recalculated when rules
change.

## Rule precedence

Rules must be deterministic and versioned. Conservative precedence:

1. cache and temporary artifacts;
2. explicit secret types and locations;
3. known application and system roots;
4. legacy backup and archive roots;
5. project roots and repository markers;
6. media candidates;
7. document candidates;
8. unknown.

A high-precedence exclusion cannot be made eligible by a lower-precedence
file-extension rule.

## First assessment

Run the read-only SQL assessment:

```bash
docker exec -i postgres \
  psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test \
  < database/assessment/scrum61_classification_inventory.sql
```

It reports:

- active files and bytes per `/volume1` root;
- preliminary conservative category counts;
- exact content-hash duplicate groups and theoretical maximum savings;
- roots participating in duplicate groups;
- repeated normalized folder basenames;
- current population inside and outside `/volume1/data`.

The duplicate savings figure is theoretical only. It does not account for
retention, backup policy, hardlinks, desired versions, restore requirements,
or whether a source root is still authoritative.

## Approval gate

Before adding a classification table:

1. review category counts and misclassifications;
2. define the authoritative root allowlist and denylist;
3. define retention requirements for backups and archives;
4. choose a small document-only pilot source;
5. approve category and scope vocabulary;
6. document how manual overrides survive rule recalculation.

No physical migration to `/volume1/data` starts in this phase.

## Read-only migration manifest

For the first document source, generate one row per exact content group:

```bash
core cleanup migration-inventory \
  --source /volume1/backup/NITRO/D/data/hugo/Documents \
  --dry-run
```

The command writes a Markdown report and CSV files below
`project/exports/migration-inventory/`. It does not copy, move, delete, or
update files or database records.

The manifest records a representative file, every matching path within the
source, exact-content copy counts, sensitivity, classification, action, and
decision reason. A backup wrapper in the source path is context only:
personal content below it can remain a migration candidate.

Known system artifacts, temporary data, secrets, and software artifacts are
excluded from migration while remaining in the general scanner inventory.
Unknown and unhashed content requires review. Sensitive personal documents
may remain migration candidates, but require a separate policy before
semantic indexing.

This phase intentionally does not propose the final directory structure
inside `/volume1/data`; that decision follows content review.

## Source-map assessment

After the baseline classification assessment, run:

```bash
docker exec -i postgres \
  psql -v ON_ERROR_STOP=1 -U hugo -d nasdb_test \
  < database/assessment/scrum61_source_map.sql
```

This second read-only assessment checks the exact target-root casing, splits
`homes` into first-level components, lists direct `/volume1` files, reports
known application/system roots, and calculates exact duplicate overlap for
each root pair and within each root.

Root-pair overlap is a source-map metric, not a deletion plan. The same
content may be intentionally retained in an authoritative collection and a
backup. Root roles and retention requirements must be approved before any
migration manifest is created.
