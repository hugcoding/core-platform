BEGIN;

DROP VIEW IF EXISTS public.v_latest_document_review;
ALTER TABLE public.document_review_events
    DROP CONSTRAINT IF EXISTS document_review_events_filename_proposal_shape_check,
    DROP COLUMN IF EXISTS target_path_conflict_details,
    DROP COLUMN IF EXISTS target_path_conflict,
    DROP COLUMN IF EXISTS filename_normalization_reasons,
    DROP COLUMN IF EXISTS proposed_filename,
    DROP COLUMN IF EXISTS proposed_filename_raw,
    DROP COLUMN IF EXISTS source_filename;

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
    target_path_input_kind, target_path_suggestion, target_path_suggestion_decision,
    batch_id, proposal_evidence, ai_proposal_id
FROM public.document_review_events
ORDER BY file_id, review_type, created_at DESC, id DESC;

COMMIT;
