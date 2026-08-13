-- SCRUM-99: privacy judgments reuse the append-only portal review contract.
BEGIN;

ALTER TABLE public.document_review_events
    DROP CONSTRAINT IF EXISTS document_review_events_review_type_check;
ALTER TABLE public.document_review_events
    ADD CONSTRAINT document_review_events_review_type_check
        CHECK (review_type IN ('target_path', 'document_family', 'lifecycle', 'privacy_classification'));

ALTER TABLE public.document_review_events
    ADD COLUMN IF NOT EXISTS proposal_privacy_classification text,
    ADD COLUMN IF NOT EXISTS corrected_privacy_classification text,
    ADD COLUMN IF NOT EXISTS privacy_rule_version text,
    ADD COLUMN IF NOT EXISTS privacy_evidence text[] NOT NULL DEFAULT '{}';

ALTER TABLE public.document_review_events
    DROP CONSTRAINT IF EXISTS document_review_events_proposal_privacy_check,
    DROP CONSTRAINT IF EXISTS document_review_events_corrected_privacy_check,
    DROP CONSTRAINT IF EXISTS document_review_events_privacy_shape_check;
ALTER TABLE public.document_review_events
    ADD CONSTRAINT document_review_events_proposal_privacy_check
        CHECK (proposal_privacy_classification IS NULL OR proposal_privacy_classification IN ('low', 'medium', 'high')),
    ADD CONSTRAINT document_review_events_corrected_privacy_check
        CHECK (corrected_privacy_classification IS NULL OR corrected_privacy_classification IN ('low', 'medium', 'high')),
    ADD CONSTRAINT document_review_events_privacy_shape_check CHECK (
        review_type <> 'privacy_classification'
        OR (proposal_privacy_classification IS NOT NULL
            AND corrected_privacy_classification IS NOT NULL
            AND privacy_rule_version IS NOT NULL)
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
    corrected_privacy_classification, privacy_rule_version, privacy_evidence
FROM public.document_review_events
ORDER BY file_id, review_type, created_at DESC, id DESC;

COMMENT ON COLUMN public.document_review_events.corrected_privacy_classification IS
    'Append-only human privacy judgment; learning evidence only, never a direct model update.';

COMMIT;
