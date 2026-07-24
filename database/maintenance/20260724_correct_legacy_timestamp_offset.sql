\set ON_ERROR_STOP on
BEGIN;

CREATE TABLE IF NOT EXISTS public.core_migration_history (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

-- The worker was stopped during conversion. This is the first row written
-- afterwards and is therefore the verified boundary between legacy and new data.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.core_migration_history
        WHERE version = '20260724_correct_legacy_timestamp_offset'
    ) THEN
        RAISE EXCEPTION 'Legacy timestamp correction was already applied';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.scan_sessions
        WHERE id = 'b7ae7bf2-0ee1-4d6f-9ec8-34c900a00899'::uuid
          AND started_at = '2026-07-24 07:23:11.195006+00'::timestamptz
    ) THEN
        RAISE EXCEPTION 'Verified post-migration boundary is missing or changed';
    END IF;
END;
$$;

UPDATE public.ai_output
SET created_at = created_at + interval '2 hours'
WHERE created_at < '2026-07-24 07:23:11.195006+00';

UPDATE public.embeddings
SET created_at = created_at + interval '2 hours'
WHERE created_at < '2026-07-24 07:23:11.195006+00';

UPDATE public.files
SET created_at = created_at + interval '2 hours'
WHERE created_at < '2026-07-24 07:23:11.195006+00';
UPDATE public.files
SET updated_at = updated_at + interval '2 hours'
WHERE updated_at < '2026-07-24 07:23:11.195006+00';
UPDATE public.files
SET deleted_at = deleted_at + interval '2 hours'
WHERE deleted_at < '2026-07-24 07:23:11.195006+00';

UPDATE public.folders
SET created_at = created_at + interval '2 hours'
WHERE created_at < '2026-07-24 07:23:11.195006+00';
UPDATE public.metadata
SET created_at = created_at + interval '2 hours'
WHERE created_at < '2026-07-24 07:23:11.195006+00';

UPDATE public.scan_sessions
SET started_at = started_at + interval '2 hours'
WHERE started_at < '2026-07-24 07:23:11.195006+00';
UPDATE public.scan_sessions
SET finished_at = finished_at + interval '2 hours'
WHERE finished_at < '2026-07-24 07:23:11.195006+00';

INSERT INTO public.core_migration_history(version)
VALUES ('20260724_correct_legacy_timestamp_offset');

COMMIT;
