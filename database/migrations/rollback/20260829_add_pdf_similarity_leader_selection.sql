BEGIN;
DROP VIEW IF EXISTS public.v_pdf_content_similarity_quarantine_handoff;
ALTER TABLE public.pdf_content_similarity_review_events DROP CONSTRAINT IF EXISTS pdf_similarity_leader_check;
ALTER TABLE public.pdf_content_similarity_review_events DROP COLUMN IF EXISTS redundant_file_ids;
ALTER TABLE public.pdf_content_similarity_review_events DROP COLUMN IF EXISTS selected_file_id;
ALTER TABLE public.pdf_content_similarity_review_events DROP CONSTRAINT IF EXISTS pdf_content_similarity_review_events_action_check;
ALTER TABLE public.pdf_content_similarity_review_events ADD CONSTRAINT pdf_content_similarity_review_events_action_check
  CHECK (action IN ('same_document_version', 'keep_separate', 'withdrawn'));
COMMIT;
