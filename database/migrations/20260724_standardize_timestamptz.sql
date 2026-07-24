BEGIN;
SET LOCAL lock_timeout = '10s';

DROP VIEW IF EXISTS public.v_file_integrity;
DROP VIEW IF EXISTS public.v_files_last_hour;
DROP VIEW IF EXISTS public.v_files_over_time_extended;
DROP VIEW IF EXISTS public.v_scan_status;
DROP VIEW IF EXISTS public.v_test_documents;

ALTER TABLE public.ai_output
    ALTER COLUMN created_at TYPE timestamptz
    USING created_at AT TIME ZONE 'Europe/Amsterdam';
ALTER TABLE public.embeddings
    ALTER COLUMN created_at TYPE timestamptz
    USING created_at AT TIME ZONE 'Europe/Amsterdam';
ALTER TABLE public.files
    ALTER COLUMN created_at TYPE timestamptz
        USING created_at AT TIME ZONE 'Europe/Amsterdam',
    ALTER COLUMN updated_at TYPE timestamptz
        USING updated_at AT TIME ZONE 'Europe/Amsterdam',
    ALTER COLUMN deleted_at TYPE timestamptz
        USING deleted_at AT TIME ZONE 'Europe/Amsterdam';
ALTER TABLE public.folders
    ALTER COLUMN created_at TYPE timestamptz
    USING created_at AT TIME ZONE 'Europe/Amsterdam';
ALTER TABLE public.metadata
    ALTER COLUMN created_at TYPE timestamptz
    USING created_at AT TIME ZONE 'Europe/Amsterdam';
ALTER TABLE public.scan_sessions
    ALTER COLUMN started_at TYPE timestamptz
        USING started_at AT TIME ZONE 'Europe/Amsterdam',
    ALTER COLUMN finished_at TYPE timestamptz
        USING finished_at AT TIME ZONE 'Europe/Amsterdam';

CREATE VIEW public.v_file_integrity AS
SELECT f.*,
    CASE
        WHEN f.path IS NULL OR f.path = '' THEN 'LEGACY_MISSING_PATH'
        WHEN f.folder_id IS NULL THEN 'INVALID_MISSING_FOLDER'
        WHEN f.hash_path IS NULL OR f.hash_path = '' THEN 'INCOMPLETE_MISSING_HASH_PATH'
        WHEN f.hash_content IS NULL OR f.hash_content = '' THEN 'INCOMPLETE_MISSING_HASH_CONTENT'
        WHEN f.mime_type IS NULL OR f.mime_type = '' THEN 'INCOMPLETE_MISSING_MIME'
        WHEN f.deleted_at IS NOT NULL THEN 'DELETED'
        ELSE 'VALID'
    END AS integrity_status
FROM public.files f;

CREATE VIEW public.v_files_last_hour AS
SELECT count(*) AS files_last_hour
FROM public.files
WHERE updated_at >= now() - interval '1 hour';

CREATE VIEW public.v_files_over_time_extended AS
WITH per_day AS (
    SELECT date(created_at AT TIME ZONE 'Europe/Amsterdam') AS file_date,
           count(*) AS files_created,
           count(*)::numeric / 24.0 AS avg_files_per_hour_that_day
    FROM public.files
    GROUP BY date(created_at AT TIME ZONE 'Europe/Amsterdam')
), global_stats AS (
    SELECT count(*) AS total_files,
           min(created_at) AS first_file,
           max(created_at) AS last_file,
           extract(epoch FROM (max(created_at) - min(created_at))) / 3600 AS hours_span
    FROM public.files
)
SELECT p.file_date, p.files_created, p.avg_files_per_hour_that_day,
       g.total_files, g.first_file, g.last_file, g.hours_span,
       CASE WHEN g.hours_span < 1 THEN NULL
            ELSE g.total_files::numeric / g.hours_span END AS avg_files_per_hour_global
FROM per_day p CROSS JOIN global_stats g
ORDER BY p.file_date;

CREATE VIEW public.v_scan_status AS
SELECT id, type, status, started_at, finished_at, files_discovered,
       jobs_enqueued, jobs_processed,
       round(jobs_processed::numeric / NULLIF(jobs_enqueued, 0)::numeric * 100, 2)
           AS progress_percent
FROM public.scan_sessions
ORDER BY started_at DESC;

CREATE VIEW public.v_test_documents AS
SELECT f.id, f.folder_id, f.filename, f.extension, f.size_bytes,
       f.created_at, f.updated_at, f.modified_at_fs, f.inode,
       f.hash_path AS xxhash, fo.path
FROM public.files f
JOIN public.folders fo ON fo.id = f.folder_id
WHERE fo.path LIKE '/volume1/backup/NITRO/D/data/hugo/Documents%';

COMMIT;
