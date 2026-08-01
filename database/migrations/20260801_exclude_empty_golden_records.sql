BEGIN;

-- Preserve an append-only explanation before removing legacy zero-byte groups.
INSERT INTO public.file_events (
    file_id, event_type, decision, signals, reason, source
)
SELECT
    g.golden_file_id,
    'GOLDEN_GROUP_REMOVED',
    'excluded_empty_file',
    jsonb_build_object(
        'content_sha256', g.content_sha256,
        'size_bytes', g.size_bytes,
        'content_group_id', g.id,
        'algorithm_version', 'golden-v2'
    ),
    'Zero-byte content has no meaningful golden-record identity.',
    'migration_20260801_exclude_empty_golden_records'
FROM public.content_groups g
WHERE g.size_bytes = 0
  AND NOT EXISTS (
      SELECT 1
      FROM public.file_events e
      WHERE e.event_type = 'GOLDEN_GROUP_REMOVED'
        AND e.decision = 'excluded_empty_file'
        AND e.source = 'migration_20260801_exclude_empty_golden_records'
        AND e.signals ->> 'content_group_id' = g.id::text
  );

DELETE FROM public.content_groups
WHERE size_bytes = 0;

UPDATE public.files
SET content_sha256 = NULL,
    content_sha256_at = NULL
WHERE size_bytes = 0
  AND (content_sha256 IS NOT NULL OR content_sha256_at IS NOT NULL);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'content_groups_nonempty_check'
          AND conrelid = 'public.content_groups'::regclass
    ) THEN
        ALTER TABLE public.content_groups
            ADD CONSTRAINT content_groups_nonempty_check CHECK (size_bytes > 0);
    END IF;
END
$$;

COMMENT ON CONSTRAINT content_groups_nonempty_check ON public.content_groups IS
    'Zero-byte files remain inventoried but are excluded from golden-record groups.';

COMMIT;
