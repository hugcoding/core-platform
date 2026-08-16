BEGIN;
DROP VIEW IF EXISTS public.v_latest_workset_ai_job;
DROP VIEW IF EXISTS public.v_workset_ai_job_summary;
DROP TABLE IF EXISTS public.workset_ai_jobs;
COMMIT;
