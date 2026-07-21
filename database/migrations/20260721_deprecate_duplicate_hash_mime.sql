BEGIN;

-- Phase 1 is intentionally non-destructive. Runtime writes have moved to
-- hash_path and files.mime_type; comments expose the compatibility contract
-- to database clients while old deployments can continue to read the fields.
COMMENT ON COLUMN public.files.xxhash IS
    'DEPRECATED: duplicate of hash_path; no longer written by metadata_worker. Retained for compatibility pending removal approval.';

COMMENT ON COLUMN public.metadata.mime_type IS
    'DEPRECATED: canonical MIME value is files.mime_type; no longer written by metadata_worker. Retained for compatibility pending removal approval.';

COMMIT;
