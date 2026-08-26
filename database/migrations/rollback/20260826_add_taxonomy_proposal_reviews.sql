BEGIN;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.document_taxonomy_proposal_reviews LIMIT 1) THEN
        RAISE EXCEPTION 'rollback blocked: taxonomy proposal decisions exist';
    END IF;
END $$;
DROP VIEW IF EXISTS public.v_active_document_taxonomy_extensions;
DROP VIEW IF EXISTS public.v_latest_document_taxonomy_proposal_review;
DROP TABLE IF EXISTS public.document_taxonomy_proposal_reviews;
DROP FUNCTION IF EXISTS public.reject_document_taxonomy_proposal_review_mutation();
COMMIT;
