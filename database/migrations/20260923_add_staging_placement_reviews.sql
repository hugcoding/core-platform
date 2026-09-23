-- SCRUM-158: explicit, append-only permission to place an unclassified file in Te beoordelen.
BEGIN;

ALTER TABLE public.document_review_events
    DROP CONSTRAINT IF EXISTS document_review_events_review_type_check;
ALTER TABLE public.document_review_events
    ADD CONSTRAINT document_review_events_review_type_check
        CHECK (review_type IN (
            'target_path', 'document_family', 'lifecycle',
            'privacy_classification', 'staging_placement'
        ));

CREATE OR REPLACE VIEW public.v_latest_staging_placement_review AS
SELECT DISTINCT ON (file_id)
    id, file_id, content_group_id, content_sha256, proposal_lifecycle,
    proposal_target_path, proposal_reason_code, decision, reviewer, created_at,
    proposal_evidence ->> 'source_path' AS source_path
FROM public.document_review_events
WHERE review_type = 'staging_placement'
ORDER BY file_id, created_at DESC, id DESC;

COMMENT ON VIEW public.v_latest_staging_placement_review IS
    'Latest explicit permission for a hash/source/lifecycle/target-bound placement in Te beoordelen.';

COMMIT;
