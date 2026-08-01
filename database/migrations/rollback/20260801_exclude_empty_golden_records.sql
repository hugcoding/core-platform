BEGIN;

ALTER TABLE public.content_groups
    DROP CONSTRAINT IF EXISTS content_groups_nonempty_check;

-- Removed zero-byte groups are deliberately not reconstructed. Their physical
-- files and file inventory rows were never changed; normal processing may only
-- recreate non-empty groups.

COMMIT;
