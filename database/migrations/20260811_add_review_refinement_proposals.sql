-- SCRUM-95: structured human proposals for controlled taxonomy refinement.
BEGIN;
ALTER TABLE public.document_review_events
    ADD COLUMN IF NOT EXISTS proposed_category_label text,
    ADD COLUMN IF NOT EXISTS proposed_family_label text,
    ADD COLUMN IF NOT EXISTS proposed_target_path text;
ALTER TABLE public.document_review_events
    DROP CONSTRAINT IF EXISTS document_review_events_proposed_category_check,
    DROP CONSTRAINT IF EXISTS document_review_events_proposed_family_check,
    DROP CONSTRAINT IF EXISTS document_review_events_proposed_path_check;
ALTER TABLE public.document_review_events
    ADD CONSTRAINT document_review_events_proposed_category_check CHECK (proposed_category_label IS NULL OR length(proposed_category_label) BETWEEN 1 AND 120),
    ADD CONSTRAINT document_review_events_proposed_family_check CHECK (proposed_family_label IS NULL OR length(proposed_family_label) BETWEEN 1 AND 120),
    ADD CONSTRAINT document_review_events_proposed_path_check CHECK (proposed_target_path IS NULL OR length(proposed_target_path) BETWEEN 1 AND 500);
CREATE OR REPLACE VIEW public.v_latest_document_review AS
SELECT DISTINCT ON (file_id, review_type)
    id, review_contract_version, channel, review_type, file_id,
    content_group_id, content_sha256, proposal_category_code,
    proposal_document_family_code, proposal_lifecycle, proposal_target_path,
    proposal_confidence, proposal_reason_code, decision,
    corrected_document_family_code, review_notes, reviewer,
    supersedes_event_id, created_at, proposed_category_label,
    proposed_family_label, proposed_target_path
FROM public.document_review_events
ORDER BY file_id, review_type, created_at DESC, id DESC;
CREATE OR REPLACE VIEW public.v_document_taxonomy_refinement_queue AS
SELECT e.id AS review_event_id, e.created_at, e.reviewer, e.file_id,
       f.filename, e.proposed_category_label, e.proposed_family_label,
       e.proposed_target_path, e.review_notes, e.decision,
       e.proposal_category_code, e.proposal_document_family_code
FROM public.document_review_events e JOIN public.files f ON f.id = e.file_id
WHERE e.proposed_category_label IS NOT NULL OR e.proposed_family_label IS NOT NULL OR e.proposed_target_path IS NOT NULL;
COMMENT ON VIEW public.v_document_taxonomy_refinement_queue IS 'Human suggestions; never changes the canonical contract automatically.';
COMMIT;
