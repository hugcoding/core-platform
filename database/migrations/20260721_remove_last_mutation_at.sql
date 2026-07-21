BEGIN;

ALTER TABLE public.files
    DROP COLUMN IF EXISTS last_mutation_at;

COMMIT;
