BEGIN;
DROP VIEW IF EXISTS public.v_active_document_lifecycle_nominations;
DROP VIEW IF EXISTS public.v_latest_document_lifecycle_nomination;
DROP TRIGGER IF EXISTS document_lifecycle_nomination_events_immutable
    ON public.document_lifecycle_nomination_events;
DROP FUNCTION IF EXISTS public.reject_document_lifecycle_nomination_mutation();
DROP TABLE IF EXISTS public.document_lifecycle_nomination_events;
-- The immutable policy snapshot intentionally remains for audit/forward recovery.
COMMIT;
