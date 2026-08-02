BEGIN;

DROP VIEW IF EXISTS public.v_semantic_golden_records;
DROP INDEX IF EXISTS public.idx_semantic_documents_file_run;
DROP INDEX IF EXISTS public.idx_semantic_runs_created_at;

COMMIT;
