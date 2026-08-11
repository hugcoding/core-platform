BEGIN;
DROP VIEW IF EXISTS public.v_document_taxonomy_refinement_queue;
DROP VIEW IF EXISTS public.v_latest_document_review;
ALTER TABLE public.document_review_events DROP COLUMN IF EXISTS corrected_category_code;
CREATE OR REPLACE VIEW public.v_latest_document_review AS
SELECT DISTINCT ON (file_id, review_type) id, review_contract_version, channel, review_type, file_id, content_group_id, content_sha256, proposal_category_code, proposal_document_family_code, proposal_lifecycle, proposal_target_path, proposal_confidence, proposal_reason_code, decision, corrected_document_family_code, review_notes, reviewer, supersedes_event_id, created_at, proposed_category_label, proposed_family_label, proposed_target_path
FROM public.document_review_events ORDER BY file_id, review_type, created_at DESC, id DESC;
CREATE OR REPLACE VIEW public.v_document_taxonomy_refinement_queue AS
SELECT e.id AS review_event_id, e.created_at, e.reviewer, e.file_id, f.filename, e.proposed_category_label, e.proposed_family_label, e.proposed_target_path, e.review_notes, e.decision, e.proposal_category_code, e.proposal_document_family_code
FROM public.document_review_events e JOIN public.files f ON f.id = e.file_id
WHERE e.proposed_category_label IS NOT NULL OR e.proposed_family_label IS NOT NULL OR e.proposed_target_path IS NOT NULL;
COMMIT;
