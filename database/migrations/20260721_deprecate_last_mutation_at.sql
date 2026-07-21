BEGIN;

COMMENT ON COLUMN public.files.last_mutation_at IS
    'DEPRECATED: updated_at is the canonical timestamp for last_mutation_type. No longer written by metadata_worker; retained for compatibility pending removal approval.';

COMMIT;
