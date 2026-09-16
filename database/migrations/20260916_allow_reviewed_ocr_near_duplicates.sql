-- Conservative OCR near-duplicate evidence remains human-reviewed, including signed PDFs.
BEGIN;

CREATE TABLE IF NOT EXISTS public.ocr_similarity_comparisons (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    left_file_id bigint NOT NULL REFERENCES public.files(id) ON DELETE RESTRICT,
    right_file_id bigint NOT NULL REFERENCES public.files(id) ON DELETE RESTRICT,
    left_content_sha256 text NOT NULL CHECK (left_content_sha256 ~ '^[0-9a-f]{64}$'),
    right_content_sha256 text NOT NULL CHECK (right_content_sha256 ~ '^[0-9a-f]{64}$'),
    normalized_identity text NOT NULL CHECK (normalized_identity <> ''),
    qualifies boolean NOT NULL,
    metrics jsonb NOT NULL CHECK (jsonb_typeof(metrics) = 'object'),
    analyzer_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (left_file_id < right_file_id),
    UNIQUE (left_file_id,right_file_id,left_content_sha256,right_content_sha256,analyzer_version)
);

DROP TRIGGER IF EXISTS ocr_similarity_comparisons_immutable ON public.ocr_similarity_comparisons;
CREATE TRIGGER ocr_similarity_comparisons_immutable
BEFORE UPDATE OR DELETE ON public.ocr_similarity_comparisons
FOR EACH ROW EXECUTE FUNCTION public.reject_pdf_similarity_mutation();

COMMENT ON TABLE public.ocr_similarity_comparisons IS
  'Append-only bounded OCR comparisons; stores hashes and scores, never extracted text.';

CREATE OR REPLACE VIEW public.v_pdf_content_similarity_groups AS
WITH current_evidence AS (
    SELECT e.*, f.filename, f.path, f.size_bytes, f.deleted_at
    FROM public.v_latest_pdf_content_similarity_evidence e
    JOIN public.files f ON f.id = e.file_id
    WHERE f.deleted_at IS NULL
      AND f.content_sha256 = e.content_sha256
      AND (NOT e.signature_present OR e.analyzer_version = 'ocr-near-duplicate-v1')
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

COMMENT ON VIEW public.v_pdf_content_similarity_groups IS
  'Human-review-only PDF groups from exact extracted text or conservative OCR near-duplicate evidence.';

COMMIT;
