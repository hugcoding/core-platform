-- Restore the previous policy that excludes every signed PDF from similarity groups.
BEGIN;

DROP TRIGGER IF EXISTS ocr_similarity_comparisons_immutable ON public.ocr_similarity_comparisons;
DROP TABLE IF EXISTS public.ocr_similarity_comparisons;

CREATE OR REPLACE VIEW public.v_pdf_content_similarity_groups AS
WITH current_evidence AS (
    SELECT e.*, f.filename, f.path, f.size_bytes, f.deleted_at
    FROM public.v_latest_pdf_content_similarity_evidence e
    JOIN public.files f ON f.id = e.file_id
    WHERE f.deleted_at IS NULL
      AND f.content_sha256 = e.content_sha256
      AND NOT e.signature_present
      AND jsonb_array_length(e.extraction_warnings) = 0
), grouped AS (
    SELECT normalized_text_sha256 AS group_key,
           min(page_count) AS page_count,
           min(normalized_text_characters) AS normalized_text_characters,
           count(*) AS available_documents,
           count(DISTINCT content_sha256) AS distinct_binary_hashes,
           array_agg(file_id ORDER BY lower(path), file_id) AS file_ids,
           array_agg(id ORDER BY lower(path), file_id) AS evidence_ids
    FROM current_evidence
    GROUP BY normalized_text_sha256
    HAVING count(*) > 1
       AND count(DISTINCT content_sha256) > 1
       AND count(DISTINCT page_text_sha256) = 1
)
SELECT g.*, r.id AS latest_review_id, r.action AS latest_review_action,
       r.selected_file_id, r.redundant_file_ids,
       r.review_notes, r.reviewer, r.created_at AS reviewed_at
FROM grouped g
LEFT JOIN public.v_latest_pdf_content_similarity_review r
  ON r.group_key = g.group_key
 AND g.file_ids <@ r.file_ids
 AND g.evidence_ids <@ r.evidence_ids;

COMMIT;
