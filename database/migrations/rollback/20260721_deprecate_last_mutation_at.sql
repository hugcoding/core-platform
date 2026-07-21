BEGIN;

COMMENT ON COLUMN public.files.last_mutation_at IS NULL;

-- Runtime rollback also requires deploying the previous metadata_worker,
-- which writes last_mutation_at together with last_mutation_type.

COMMIT;
