-- SCRUM-115: append-only PDF content-similarity evidence and human review.
BEGIN;

CREATE TABLE IF NOT EXISTS public.pdf_content_similarity_evidence (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id bigint NOT NULL REFERENCES public.files(id) ON DELETE RESTRICT,
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    normalized_text_sha256 text NOT NULL CHECK (normalized_text_sha256 ~ '^[0-9a-f]{64}$'),
    page_text_sha256 jsonb NOT NULL CHECK (jsonb_typeof(page_text_sha256) = 'array'),
    page_count integer NOT NULL CHECK (page_count > 0),
    normalized_text_characters integer NOT NULL CHECK (normalized_text_characters > 0),
    metadata_snapshot jsonb NOT NULL CHECK (jsonb_typeof(metadata_snapshot) = 'object'),
    pdf_document_id jsonb NOT NULL CHECK (jsonb_typeof(pdf_document_id) = 'array'),
    signature_present boolean NOT NULL,
    extraction_warnings jsonb NOT NULL CHECK (jsonb_typeof(extraction_warnings) = 'array'),
    analyzer_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (file_id, content_sha256, analyzer_version)
);

CREATE TABLE IF NOT EXISTS public.pdf_content_similarity_review_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key uuid NOT NULL UNIQUE,
    group_key text NOT NULL CHECK (group_key ~ '^[0-9a-f]{64}$'),
    action text NOT NULL CHECK (action IN ('same_document_version', 'keep_separate', 'withdrawn')),
    file_ids bigint[] NOT NULL CHECK (cardinality(file_ids) > 1),
    evidence_ids uuid[] NOT NULL CHECK (cardinality(evidence_ids) = cardinality(file_ids)),
    review_notes text NOT NULL DEFAULT '' CHECK (length(review_notes) <= 2000),
    reviewer text NOT NULL,
    supersedes_event_id uuid REFERENCES public.pdf_content_similarity_review_events(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION public.reject_pdf_similarity_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'PDF similarity evidence and reviews are append-only';
END;
$$;

DROP TRIGGER IF EXISTS pdf_content_similarity_evidence_immutable ON public.pdf_content_similarity_evidence;
CREATE TRIGGER pdf_content_similarity_evidence_immutable
BEFORE UPDATE OR DELETE ON public.pdf_content_similarity_evidence
FOR EACH ROW EXECUTE FUNCTION public.reject_pdf_similarity_mutation();
DROP TRIGGER IF EXISTS pdf_content_similarity_reviews_immutable ON public.pdf_content_similarity_review_events;
CREATE TRIGGER pdf_content_similarity_reviews_immutable
BEFORE UPDATE OR DELETE ON public.pdf_content_similarity_review_events
FOR EACH ROW EXECUTE FUNCTION public.reject_pdf_similarity_mutation();

CREATE OR REPLACE VIEW public.v_latest_pdf_content_similarity_evidence AS
SELECT DISTINCT ON (file_id) *
FROM public.pdf_content_similarity_evidence
ORDER BY file_id, created_at DESC, id DESC;

CREATE OR REPLACE VIEW public.v_latest_pdf_content_similarity_review AS
SELECT DISTINCT ON (group_key) *
FROM public.pdf_content_similarity_review_events
ORDER BY group_key, created_at DESC, id DESC;

CREATE OR REPLACE VIEW public.v_pdf_content_similarity_groups AS
WITH current_evidence AS (
    SELECT e.*, f.filename, f.path, f.size_bytes, f.deleted_at
    FROM public.v_latest_pdf_content_similarity_evidence e
    JOIN public.files f ON f.id = e.file_id
    WHERE f.deleted_at IS NULL AND f.content_sha256 = e.content_sha256
      AND NOT e.signature_present AND jsonb_array_length(e.extraction_warnings) = 0
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
    HAVING count(*) > 1 AND count(DISTINCT content_sha256) > 1
       AND count(DISTINCT page_text_sha256) = 1
)
SELECT g.*, r.id AS latest_review_id, r.action AS latest_review_action,
       r.review_notes, r.reviewer, r.created_at AS reviewed_at
FROM grouped g
LEFT JOIN public.v_latest_pdf_content_similarity_review r
  ON r.group_key = g.group_key
 AND r.file_ids = g.file_ids
 AND r.evidence_ids = g.evidence_ids;

COMMENT ON TABLE public.pdf_content_similarity_evidence IS
  'Append-only technical PDF evidence; extracted document text is deliberately not stored.';
COMMENT ON VIEW public.v_pdf_content_similarity_groups IS
  'Advisory candidates only. This view never authorizes deletion, migration or golden-record changes.';
COMMIT;
