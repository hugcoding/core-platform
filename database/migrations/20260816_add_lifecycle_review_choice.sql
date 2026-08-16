-- SCRUM-104: append-only human lifecycle decisions for every workset status.
BEGIN;

ALTER TABLE public.document_review_events
    ADD COLUMN IF NOT EXISTS corrected_lifecycle text,
    ADD COLUMN IF NOT EXISTS lifecycle_active_until timestamptz;

ALTER TABLE public.document_review_events
    DROP CONSTRAINT IF EXISTS document_review_events_corrected_lifecycle_check;
ALTER TABLE public.document_review_events
    ADD CONSTRAINT document_review_events_corrected_lifecycle_check CHECK (
        corrected_lifecycle IS NULL
        OR corrected_lifecycle IN ('active', 'archive', 'needs_review')
    );
ALTER TABLE public.document_review_events
    DROP CONSTRAINT IF EXISTS document_review_events_lifecycle_active_until_check;
ALTER TABLE public.document_review_events
    ADD CONSTRAINT document_review_events_lifecycle_active_until_check CHECK (
        lifecycle_active_until IS NULL OR corrected_lifecycle = 'active'
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
    filename_normalization_reasons, target_path_conflict, target_path_conflict_details,
    corrected_lifecycle, lifecycle_active_until
FROM public.document_review_events
ORDER BY file_id, review_type, created_at DESC, id DESC;

COMMENT ON COLUMN public.document_review_events.corrected_lifecycle IS
    'Append-only human lifecycle decision; never changes a file or workset status directly.';
COMMENT ON COLUMN public.document_review_events.lifecycle_active_until IS
    'Optional end of a human active-period; null means no explicit end was supplied.';

COMMIT;
