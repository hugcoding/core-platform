-- SCRUM-69 rollback. This removes derived temporal evidence, never source files.
BEGIN;

DROP VIEW IF EXISTS public.v_file_temporal_profile;
DROP TABLE IF EXISTS public.file_date_evidence;

COMMIT;
