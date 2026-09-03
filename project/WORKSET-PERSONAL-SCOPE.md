# Workset scope after migration

The v1 policy only includes OneDrive import Documenten. Moving a golden record
into Persoonlijk therefore removes it from v_active_document_workset, including
the target-path-preview endpoint (409: no longer a workset candidate).

The v2 policy retains import scope and adds Persoonlijk/Actief, Inactief and the
legacy Te beoordelen folder. Nested review folders are included. Quarantine and
unrelated collections are not included. Golden-record, extension, temporal and
review-state filters remain unchanged; a folder move does not reset a review.

## Activate after merge and pull

Use the same environment as the dashboard (this NAS currently uses acceptance).
Review the dry-run plan before applying. This appends an immutable policy;
it does not move files or modify prior reviews. No dashboard rebuild is needed.

```sh
core git pull
core policy seed --environment acceptance --dry-run
core policy seed --environment acceptance --apply
```

Refresh the Workset, locate file 3361595 under Inactive with the appropriate
review filter, then change category/family and verify its target preview.
An already approved execution batch retains its original immutable plan.

Verify activation:

```sql
SELECT environment, policy_version, configuration->'source_roots'
FROM v_current_policies WHERE policy_code = 'active_document_workset';
SELECT file_id, path, workset_status FROM v_active_document_workset
WHERE file_id = 3361595;
```

Rolling back requires a NEW policy snapshot with a later effective_from and
distinct configuration checksum; reseeding v1 does not supersede v2.
