BEGIN;
DROP VIEW IF EXISTS public.v_document_taxonomy_refinement_queue;
DROP VIEW IF EXISTS public.v_latest_document_review;
ALTER TABLE public.document_review_events DROP COLUMN IF EXISTS proposed_category_label, DROP COLUMN IF EXISTS proposed_family_label, DROP COLUMN IF EXISTS proposed_target_path;
CREATE OR REPLACE VIEW public.v_latest_document_review AS
SELECT DISTINCT ON (file_id, review_type) id, review_contract_version, channel, review_type, file_id, content_group_id, content_sha256, proposal_category_code, proposal_document_family_code, proposal_lifecycle, proposal_target_path, proposal_confidence, proposal_reason_code, decision, corrected_document_family_code, review_notes, reviewer, supersedes_event_id, created_at
FROM public.document_review_events ORDER BY file_id, review_type, created_at DESC, id DESC;
COMMIT;
