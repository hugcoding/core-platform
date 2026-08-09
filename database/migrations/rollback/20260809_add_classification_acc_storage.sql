BEGIN;
DROP VIEW IF EXISTS public.v_current_file_classification;
DROP TABLE IF EXISTS public.classification_reviews;
DROP TABLE IF EXISTS public.classification_proposals;
DROP TABLE IF EXISTS public.classification_runs;
COMMIT;
