BEGIN;

-- Roll back the database-visible deprecation markers. Runtime rollback also
-- requires deploying the previous metadata_worker version that dual-writes
-- files.xxhash and metadata.mime_type.
COMMENT ON COLUMN public.files.xxhash IS NULL;
COMMENT ON COLUMN public.metadata.mime_type IS NULL;

COMMIT;
