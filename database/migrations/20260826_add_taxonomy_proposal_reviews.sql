-- Controlled promotion of human taxonomy proposals; append-only and file-safe.
BEGIN;

CREATE TABLE IF NOT EXISTS public.document_taxonomy_proposal_reviews (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key uuid NOT NULL UNIQUE,
    proposal_key text NOT NULL,
    proposal_type text NOT NULL CHECK (proposal_type IN ('category', 'family')),
    proposed_label text NOT NULL CHECK (length(proposed_label) BETWEEN 1 AND 120),
    normalized_label text NOT NULL CHECK (length(normalized_label) BETWEEN 1 AND 120),
    taxonomy_code text NOT NULL CHECK (taxonomy_code ~ '^custom_[a-z0-9_]{1,73}$'),
    category_code text NULL,
    decision text NOT NULL CHECK (decision IN ('accepted', 'rejected')),
    source_review_event_ids uuid[] NOT NULL CHECK (cardinality(source_review_event_ids) > 0),
    review_notes text NULL CHECK (review_notes IS NULL OR length(review_notes) <= 2000),
    reviewer text NOT NULL,
    supersedes_event_id uuid NULL REFERENCES public.document_taxonomy_proposal_reviews(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((proposal_type = 'category' AND category_code IS NULL)
        OR (proposal_type = 'family' AND category_code IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS document_taxonomy_proposal_reviews_key_created_idx
    ON public.document_taxonomy_proposal_reviews(proposal_key, created_at DESC);

DROP TRIGGER IF EXISTS document_taxonomy_proposal_reviews_immutable
    ON public.document_taxonomy_proposal_reviews;
CREATE OR REPLACE FUNCTION public.reject_document_taxonomy_proposal_review_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'document taxonomy proposal reviews are append-only';
END;
$$;
CREATE TRIGGER document_taxonomy_proposal_reviews_immutable
BEFORE UPDATE OR DELETE ON public.document_taxonomy_proposal_reviews
FOR EACH ROW EXECUTE FUNCTION public.reject_document_taxonomy_proposal_review_mutation();

CREATE OR REPLACE VIEW public.v_latest_document_taxonomy_proposal_review AS
SELECT DISTINCT ON (proposal_key) *
FROM public.document_taxonomy_proposal_reviews
ORDER BY proposal_key, created_at DESC, id DESC;

CREATE OR REPLACE VIEW public.v_active_document_taxonomy_extensions AS
SELECT proposal_key, proposal_type, proposed_label, normalized_label,
       taxonomy_code, category_code, source_review_event_ids,
       reviewer, created_at
FROM public.v_latest_document_taxonomy_proposal_review
WHERE decision = 'accepted';

COMMENT ON TABLE public.document_taxonomy_proposal_reviews IS
    'Append-only human decisions promoting review proposals into the portal taxonomy; never mutates files or prior reviews.';
COMMENT ON VIEW public.v_active_document_taxonomy_extensions IS
    'Currently accepted database-backed taxonomy extensions for portal choices.';

COMMIT;
