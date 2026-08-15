-- SCRUM-98: append-only evidence for safe, proposal-only filename changes.
BEGIN;

ALTER TABLE public.document_review_events
    ADD COLUMN IF NOT EXISTS source_filename text,
    ADD COLUMN IF NOT EXISTS proposed_filename_raw text,
    ADD COLUMN IF NOT EXISTS proposed_filename text,
    ADD COLUMN IF NOT EXISTS filename_normalization_reasons jsonb,
    ADD COLUMN IF NOT EXISTS target_path_conflict boolean,
    ADD COLUMN IF NOT EXISTS target_path_conflict_details jsonb;

ALTER TABLE public.document_review_events
    DROP CONSTRAINT IF EXISTS document_review_events_filename_proposal_shape_check;
ALTER TABLE public.document_review_events
    ADD CONSTRAINT document_review_events_filename_proposal_shape_check CHECK (
        (proposed_filename IS NULL AND proposed_filename_raw IS NULL)
        OR (
            review_type = 'target_path'
            AND source_filename IS NOT NULL AND length(source_filename) BETWEEN 1 AND 255
            AND proposed_filename_raw IS NOT NULL AND length(proposed_filename_raw) BETWEEN 1 AND 255
            AND proposed_filename IS NOT NULL AND length(proposed_filename) BETWEEN 1 AND 255
            AND jsonb_typeof(filename_normalization_reasons) = 'array'
            AND target_path_conflict IS NOT NULL
            AND jsonb_typeof(target_path_conflict_details) = 'object'
        )
    );

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
    batch_id, proposal_evidence, ai_proposal_id,
    source_filename, proposed_filename_raw, proposed_filename,
    filename_normalization_reasons, target_path_conflict, target_path_conflict_details
FROM public.document_review_events
ORDER BY file_id, review_type, created_at DESC, id DESC;

COMMENT ON COLUMN public.document_review_events.proposed_filename IS
    'Normalized human filename proposal only; never causes a filesystem rename.';

COMMIT;
