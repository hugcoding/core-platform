BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.files
        WHERE last_mutation_type = 'REPLACED'
    ) THEN
        RAISE EXCEPTION
            'Rollback blocked: files contains REPLACED mutations';
    END IF;
END;
$$;

ALTER TABLE public.files
    DROP CONSTRAINT IF EXISTS files_last_mutation_type_check;

ALTER TABLE public.files
    ADD CONSTRAINT files_last_mutation_type_check
    CHECK (last_mutation_type IN (
        'UNKNOWN', 'CREATED', 'MODIFIED', 'RENAMED',
        'MOVED', 'RESTORED', 'DELETED'
    ));

COMMIT;
