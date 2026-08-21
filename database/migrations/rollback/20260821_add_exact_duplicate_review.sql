BEGIN;
DROP VIEW IF EXISTS public.v_exact_duplicate_review_handoff;
DROP VIEW IF EXISTS public.v_exact_duplicate_review_groups;
DROP VIEW IF EXISTS public.v_latest_exact_duplicate_review;
DROP TRIGGER IF EXISTS exact_duplicate_review_events_immutable ON public.exact_duplicate_review_events;
DROP FUNCTION IF EXISTS public.reject_exact_duplicate_review_mutation();
DROP TABLE IF EXISTS public.exact_duplicate_review_events;
COMMIT;
