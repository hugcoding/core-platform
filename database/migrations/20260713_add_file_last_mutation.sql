BEGIN;

-- Existing rows remain UNKNOWN until the worker observes their next mutation.
ALTER TABLE public.files
    ADD COLUMN IF NOT EXISTS last_mutation_type text,
    ADD COLUMN IF NOT EXISTS last_mutation_at timestamp without time zone;

UPDATE public.files
SET last_mutation_type = 'UNKNOWN'
WHERE last_mutation_type IS NULL;

ALTER TABLE public.files
    ALTER COLUMN last_mutation_type SET DEFAULT 'UNKNOWN',
    ALTER COLUMN last_mutation_type SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'files_last_mutation_type_check'
          AND conrelid = 'public.files'::regclass
    ) THEN
        ALTER TABLE public.files
            ADD CONSTRAINT files_last_mutation_type_check
            CHECK (last_mutation_type IN (
                'UNKNOWN', 'CREATED', 'MODIFIED', 'RENAMED',
                'MOVED', 'RESTORED', 'DELETED'
            ));
    END IF;
END;
$$;

COMMIT;
