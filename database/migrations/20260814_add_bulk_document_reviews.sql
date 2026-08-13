-- SCRUM-98: auditable bulk approval over explicitly selected visible proposals.
BEGIN;

CREATE TABLE IF NOT EXISTS public.document_review_batches (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key text NOT NULL UNIQUE,
    channel text NOT NULL CHECK (channel = 'workset_portal'),
    decision text NOT NULL CHECK (decision = 'accepted'),
    document_count integer NOT NULL CHECK (document_count BETWEEN 1 AND 50),
    selection_snapshot jsonb NOT NULL,
    reviewer text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.document_review_events
    ADD COLUMN IF NOT EXISTS batch_id uuid REFERENCES public.document_review_batches(id);
CREATE INDEX IF NOT EXISTS document_review_events_batch_idx
    ON public.document_review_events(batch_id) WHERE batch_id IS NOT NULL;

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
    batch_id
FROM public.document_review_events
ORDER BY file_id, review_type, created_at DESC, id DESC;

COMMIT;
