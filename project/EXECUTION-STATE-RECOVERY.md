# Repeated execution candidates and premature completion

## Cause

Both planned and queued were inserted in one transaction using now(). Equal
timestamps were resolved by random UUID. A queued item could therefore appear
planned; the worker skipped it and still recorded completed. The September 4
batch 8112f65c-049c-472c-b93d-171fb7c8483d demonstrates this for files 3362041
and 3362166. No historical audit events are edited or deleted by the fix.

## Correction

- New timestamps use clock_timestamp, with an identity sequence for ordering.
- Historical planned/queued ties explicitly resolve to queued.
- Unknown/unapproved item states pause execution instead of being skipped.
- Before completion, the worker rereads every item and checks terminal states.
- Existing completed batches with outstanding items display as incomplete;
  they are not automatically replayed by this migration.
- Preview checks source size and existing destination without hashing all files.
  These checks rerun at approval and the executor still validates content.
- Other previously blocked identical plans are held until their evidence changes.
- Blockages have visible explanations. Rollback is hidden when nothing succeeded.

## Read-only checks on the reported files

- 3361738: source CV is 197072 bytes; existing target is 602977 bytes. SHA-256
  differs: not an exact duplicate. Requires a distinct target/explicit review.
- 3362041: expected 22284 bytes, actual 22380 bytes; SHA-256 differs. Requires
  refreshed inventory and new approval, never changing the old immutable plan.
- 3362166: size 1128425 and hash match the plan; target absent. Can be offered
  again for explicit approval after fixing event order.

## Deployment

Apply database/migrations/20260904_execution_event_order.sql and rebuild dashboard
and controlled_execution_worker. First check for running/approved batches: this
fix must not unexpectedly replay historical completed batches. No file repair
or automatic reapproval is part of deployment.

Regression coverage includes repeated preflight, persistent hash failures,
unknown-state pause, completion guard, and isolated PostgreSQL + filesystem
integration with equal timestamps where planned is inserted after queued.
