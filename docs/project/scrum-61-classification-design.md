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

Create the second, document-focused manifest from the latest exact-content
manifest:

```bash
core cleanup migration-review --manifest latest --dry-run
```

Every exact-content group remains represented. The second manifest assigns a
review class:

- `personal_document`;
- `project_or_technical`;
- `manual_review`;
- `deferred_media`.

Folder names such as `backup`, `archive`, or `CloudStation` never determine
this class. Archives, cloud-document pointers, credentials, and unknown
formats remain manual-review items. The command is read-only and does not
propose target paths.

Create the non-mutating migration proposal:

```bash
core cleanup migration-proposal --manifest latest --dry-run
```

This separates standard and sensitive document waves, retains project and
technical content in the inventory, and creates focused review lists for
archives, cloud pointers, credentials, and unresolved formats. Missing
content hashes block copy planning. Cisco icon-library EPS assets are retained
as technical data based on their specific content path; a generic `backup`
folder name never affects the proposal.

The proposal still contains no target paths and cannot copy, move, update, or
delete anything.

## Read-only document copy plan

Generate proposed target paths for the standard and sensitive document waves:

```bash
core cleanup copy-plan --manifest latest --dry-run
```

The plan uses `/volume1/data` and the approved top-level buckets under
`documents/` and `sensitive/`. It emits one row per exact-content group and
retains all source paths as provenance.

Target paths are compared case-insensitively for SMB compatibility. Different
hashes proposing the same path are both preserved with an eight-character
content-hash suffix before the extension. This prevents overwrites while
retaining both versions for later content review.
Existing physical target paths are blocked without reading or overwriting
them. Unclear documents are proposed under `documents/unsorted` and require
manual target review. Sensitive documents are placed below `sensitive/` and
remain blocked from semantic processing.

Meaningful subdirectories are preserved below each bucket to retain context
and avoid flattening unrelated files onto the same target name. Generic
`CloudStation` wrappers and the source category component are removed.
Recognized build metadata and documents below the explicit `Systeem` folder
remain project/technical data. Strong source evidence such as `Geldzaken`,
`Gezondheid & Voeding`, and `Officiële documenten` upgrades the target to the
corresponding sensitive bucket even when the earlier extension-only proposal
did not mark the file sensitive.

The command also emits a `folder-plan-*.csv`. This is a read-only mapping from
every contributing source directory to its proposed target directory, with
the target bucket, number of content groups, proposed actions, and
classification reasons. It is a structure proposal only: empty source
directories are not represented and no target directories are created.

The command creates reports only. It does not create directories or copy,
move, overwrite, update, or delete files.

## Golden records before target classification

Generate a read-only proposal that selects one source record per exact
content-hash group:

```bash
core cleanup golden-records \
  --source /volume1/backup/NITRO/D/data/hugo/Documents \
  --dry-run
```

The golden-record score prefers trustworthy original locations and filenames
and penalizes legacy wrappers, temporary locations, exports, archives, and
copy-like filenames. Every exact-content group always receives exactly one
golden record. Equal top scores use a deterministic path and file-id
tiebreaker, retain `low` confidence for visibility, and do not block the
later copy. Every alternative source and the score explanation remain in the
manifest. Alternative physical files remain untouched at their existing NAS
locations.

Target paths deliberately remain empty in this phase. The next
content-classification phase determines the compact Dutch target hierarchy
from the files themselves; source directory names are supporting evidence
only.

Durable decisions are stored in `content_groups` and
`content_group_members`. `content_groups.golden_file_id` is the single
authoritative selection. A deferred composite foreign key guarantees that
the selected file is also a recorded member of the same group. The
`v_content_group_members` view derives `is_golden`, avoiding two independent
sources of truth. Scores, ranks, reasons, source-path snapshots, confidence,
and the algorithm version preserve the audit trail. Proposed Dutch target
paths belong to a later migration-plan structure and are deliberately not
stored in these identity tables.

### Full hash and event-driven reevaluation

`files.hash_content` is a fast xxHash64 signal over the first 1024 bytes and
must never be used as exact-duplicate proof. Supported documents additionally
receive a full-file SHA-256 in `files.content_sha256`. Golden-record groups
are keyed only by `content_sha256` plus `size_bytes`.

The metadata worker reuses a stored SHA-256 when size and filesystem mtime are
unchanged. Otherwise it streams the complete document in 1 MiB chunks. The
following mutations reevaluate only the affected old and new content groups:
`CREATED`, `MODIFIED`, `RENAMED`, `MOVED`, `RESTORED`, and `DELETED`.
Renames and moves are reevaluated even when content is unchanged because the
source path affects the score.

When a group changes, the worker deterministically ranks all active members,
updates the single `golden_file_id`, rebuilds the member snapshot, and emits
`GOLDEN_RECORD_SELECTED`, `GOLDEN_RECORD_CHANGED`, or
`GOLDEN_GROUP_REMOVED` into `file_events`. Alternative physical files remain
untouched.

An ordinary full scan only enqueues changed filesystem signatures. Existing
documents that predate `content_sha256` therefore use the targeted one-time
backfill:

```bash
core scanner hash-backfill \
  --source /volume1/backup/NITRO/D/data/hugo/Documents
```

The scanner queries only active supported documents with a missing full hash
below the selected source and queues those paths for the metadata worker. It
does not modify, move, or delete physical files.

During the document-development phase, `SCAN_ROOTS` is an explicit allowlist:

```text
/volume1/backup/NITRO/D/data/hugo/Documents,/volume1/data
```

Full and interval scans operate only below these roots. Reconciliation is
scoped to the same roots, so files elsewhere on the NAS remain physically
untouched and keep their existing database state rather than being marked
deleted merely because they are temporarily outside the active scope.

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

## Content-classification inventory

After full hashes and persisted golden records are complete, create an
extractor inventory for golden records only:

```bash
core cleanup classification-inventory \
  --source /volume1/backup/NITRO/D/data/hugo/Documents \
  --dry-run
```

The inventory assigns an extraction route for modern Office, PDF, plain-text,
ODF, RTF, and legacy Office formats. Category and Dutch target path remain
`pending_content_extraction`: content must be read before classification, and
the old source path is supporting evidence only. Processing remains local;
embeddings and external AI are disabled.

Run transient local extraction and rule-based classification in the isolated
tool container:

```bash
core cleanup classification-extract --manifest latest --dry-run
```

The container mounts `/volume1` read-only and stores only statistics,
classification signals, confidence, OCR status, and errors. Raw extracted
text is discarded after each document and never written to CSV or
PostgreSQL. Legacy Office formats remain `conversion_required`; embeddings
and external AI stay disabled.
