BEGIN;

ALTER TABLE public.files
    ADD COLUMN IF NOT EXISTS content_sha256 text,
    ADD COLUMN IF NOT EXISTS content_sha256_at timestamptz;

CREATE INDEX IF NOT EXISTS files_content_sha256_size_active_idx
    ON public.files (content_sha256, size_bytes)
    WHERE deleted_at IS NULL AND content_sha256 IS NOT NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'content_groups'
          AND column_name = 'hash_content'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'content_groups'
          AND column_name = 'content_sha256'
    ) THEN
        ALTER TABLE public.content_groups
            RENAME COLUMN hash_content TO content_sha256;
    END IF;
END
$$;

CREATE OR REPLACE VIEW public.v_content_group_members AS
SELECT
    m.content_group_id,
    g.content_sha256,
    g.size_bytes,
    m.file_id,
    m.source_path_snapshot,
    m.selection_score,
    m.selection_rank,
    (m.file_id = g.golden_file_id) AS is_golden,
    m.selection_reasons,
    g.confidence,
    g.selection_status,
    g.algorithm_version,
    g.selected_at,
    m.assessed_at
FROM public.content_group_members m
JOIN public.content_groups g ON g.id = m.content_group_id;

COMMENT ON COLUMN public.files.content_sha256 IS
    'Full-file SHA-256 used as exact-content evidence for golden records.';
COMMENT ON COLUMN public.files.hash_content IS
    'Fast xxHash64 of the first 1024 bytes; identity signal only, not exact-duplicate proof.';

COMMIT;
