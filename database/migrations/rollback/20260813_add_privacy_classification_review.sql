BEGIN;

DROP VIEW IF EXISTS public.v_latest_document_review;

-- These rows depend on the columns removed below. Existing target-path history is retained.
DELETE FROM public.document_review_events WHERE review_type = 'privacy_classification';

ALTER TABLE public.document_review_events
    DROP CONSTRAINT IF EXISTS document_review_events_privacy_shape_check,
    DROP CONSTRAINT IF EXISTS document_review_events_corrected_privacy_check,
    DROP CONSTRAINT IF EXISTS document_review_events_proposal_privacy_check,
    DROP CONSTRAINT IF EXISTS document_review_events_review_type_check,
    DROP COLUMN IF EXISTS privacy_evidence,
    DROP COLUMN IF EXISTS privacy_rule_version,
    DROP COLUMN IF EXISTS corrected_privacy_classification,
    DROP COLUMN IF EXISTS proposal_privacy_classification;
ALTER TABLE public.document_review_events
    ADD CONSTRAINT document_review_events_review_type_check
        CHECK (review_type IN ('target_path', 'document_family', 'lifecycle'));

CREATE OR REPLACE VIEW public.v_latest_document_review AS
SELECT DISTINCT ON (file_id, review_type)
    id, review_contract_version, channel, review_type, file_id,
    content_group_id, content_sha256, proposal_category_code,
    proposal_document_family_code, proposal_lifecycle, proposal_target_path,
    proposal_confidence, proposal_reason_code, decision,
    corrected_document_family_code, review_notes, reviewer,
    supersedes_event_id, created_at, proposed_category_label,
    proposed_family_label, proposed_target_path, corrected_category_code,
    proposed_target_path_raw
FROM public.document_review_events
ORDER BY file_id, review_type, created_at DESC, id DESC;

COMMIT;
