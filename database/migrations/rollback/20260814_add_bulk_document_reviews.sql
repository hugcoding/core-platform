BEGIN;

DROP VIEW IF EXISTS public.v_latest_document_review;
DROP INDEX IF EXISTS public.document_review_events_batch_idx;
ALTER TABLE public.document_review_events DROP COLUMN IF EXISTS batch_id;
DROP TABLE IF EXISTS public.document_review_batches;

CREATE OR REPLACE VIEW public.v_latest_document_review AS
SELECT DISTINCT ON (file_id, review_type)
    id, review_contract_version, channel, review_type, file_id,
    content_group_id, content_sha256, proposal_category_code,
    proposal_document_family_code, proposal_lifecycle, proposal_target_path,
    proposal_confidence, proposal_reason_code, decision,
    corrected_document_family_code, review_notes, reviewer,
    supersedes_event_id, created_at, proposed_category_label,
    proposed_family_label, proposed_target_path, corrected_category_code,
    proposed_target_path_raw, proposal_privacy_classification,
    corrected_privacy_classification, privacy_rule_version, privacy_evidence,
    target_path_input_kind, target_path_suggestion, target_path_suggestion_decision
FROM public.document_review_events
ORDER BY file_id, review_type, created_at DESC, id DESC;

COMMIT;
