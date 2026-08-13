-- SCRUM-98: append-only audit evidence for the controlled target-path assistant.
BEGIN;

ALTER TABLE public.document_review_events
    ADD COLUMN IF NOT EXISTS target_path_input_kind text,
    ADD COLUMN IF NOT EXISTS target_path_suggestion text,
    ADD COLUMN IF NOT EXISTS target_path_suggestion_decision text;

ALTER TABLE public.document_review_events
    DROP CONSTRAINT IF EXISTS document_review_events_target_path_input_kind_check,
    DROP CONSTRAINT IF EXISTS document_review_events_target_path_suggestion_decision_check;
ALTER TABLE public.document_review_events
    ADD CONSTRAINT document_review_events_target_path_input_kind_check
        CHECK (target_path_input_kind IS NULL OR target_path_input_kind IN ('directory', 'full_path')),
    ADD CONSTRAINT document_review_events_target_path_suggestion_decision_check
        CHECK (target_path_suggestion_decision IS NULL OR target_path_suggestion_decision IN
               ('accepted', 'dismissed', 'new_path', 'no_suggestion'));

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

COMMENT ON COLUMN public.document_review_events.target_path_suggestion_decision IS
    'Explicit human decision about an advisory path suggestion; never silently applies a rule.';

COMMIT;
