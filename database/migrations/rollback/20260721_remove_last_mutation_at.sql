BEGIN;

ALTER TABLE public.files
    ADD COLUMN IF NOT EXISTS last_mutation_at timestamp without time zone;

UPDATE public.files
SET last_mutation_at = updated_at
WHERE last_mutation_type <> 'UNKNOWN'
  AND last_mutation_at IS NULL;

COMMIT;
