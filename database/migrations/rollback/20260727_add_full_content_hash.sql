BEGIN;

DROP VIEW IF EXISTS public.v_content_group_members;
DROP INDEX IF EXISTS public.files_content_sha256_size_active_idx;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'content_groups'
          AND column_name = 'content_sha256'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'content_groups'
          AND column_name = 'hash_content'
    ) THEN
        ALTER TABLE public.content_groups
            RENAME COLUMN content_sha256 TO hash_content;
    END IF;
END
$$;

ALTER TABLE public.files
    DROP COLUMN IF EXISTS content_sha256_at,
    DROP COLUMN IF EXISTS content_sha256;

COMMIT;
