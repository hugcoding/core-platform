BEGIN;

ALTER TABLE public.files
    DROP CONSTRAINT IF EXISTS files_last_mutation_type_check;

ALTER TABLE public.files
    ADD CONSTRAINT files_last_mutation_type_check
    CHECK (last_mutation_type IN (
        'UNKNOWN', 'CREATED', 'MODIFIED', 'RENAMED',
        'MOVED', 'REPLACED', 'RESTORED', 'DELETED'
    ));

COMMIT;
