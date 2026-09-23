BEGIN;

DROP VIEW IF EXISTS public.v_latest_staging_placement_review;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.document_review_events
        WHERE review_type = 'staging_placement'
    ) THEN
        RAISE EXCEPTION 'Cannot roll back SCRUM-158 while staging placement reviews exist';
    END IF;
END $$;

ALTER TABLE public.document_review_events
    DROP CONSTRAINT IF EXISTS document_review_events_review_type_check;
ALTER TABLE public.document_review_events
    ADD CONSTRAINT document_review_events_review_type_check
        CHECK (review_type IN ('target_path', 'document_family', 'lifecycle', 'privacy_classification'));

COMMIT;
