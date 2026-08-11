-- SCRUM-95/94: append-only human judgments shared by portal and future quiz.
BEGIN;

CREATE TABLE IF NOT EXISTS public.document_review_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key text NOT NULL UNIQUE,
    review_contract_version text NOT NULL,
    channel text NOT NULL CHECK (channel IN ('workset_portal', 'document_quiz')),
    review_type text NOT NULL CHECK (review_type IN ('target_path', 'document_family', 'lifecycle')),
    file_id bigint NOT NULL REFERENCES public.files(id) ON DELETE RESTRICT,
    content_group_id uuid NOT NULL REFERENCES public.content_groups(id) ON DELETE RESTRICT,
    content_sha256 text NOT NULL,
    proposal_category_code text,
    proposal_document_family_code text,
    proposal_lifecycle text,
    proposal_target_path text,
    proposal_confidence text,
    proposal_reason_code text,
    decision text NOT NULL CHECK (decision IN ('accepted', 'rejected', 'needs_review', 'passed')),
    corrected_document_family_code text,
    review_notes text,
    reviewer text NOT NULL,
    supersedes_event_id uuid REFERENCES public.document_review_events(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (length(idempotency_key) BETWEEN 16 AND 128),
    CHECK (length(reviewer) BETWEEN 1 AND 100),
    CHECK (review_notes IS NULL OR length(review_notes) <= 2000)
);

CREATE INDEX IF NOT EXISTS document_review_events_file_created_idx
    ON public.document_review_events (file_id, created_at DESC, id DESC);

CREATE OR REPLACE VIEW public.v_latest_document_review AS
SELECT DISTINCT ON (file_id, review_type)
    id, review_contract_version, channel, review_type, file_id,
    content_group_id, content_sha256, proposal_category_code,
    proposal_document_family_code, proposal_lifecycle, proposal_target_path,
    proposal_confidence, proposal_reason_code, decision,
    corrected_document_family_code, review_notes, reviewer,
    supersedes_event_id, created_at
FROM public.document_review_events
ORDER BY file_id, review_type, created_at DESC, id DESC;

COMMENT ON TABLE public.document_review_events IS
    'Append-only human judgments; never directly tunes models or mutates files.';
COMMENT ON VIEW public.v_latest_document_review IS
    'Latest judgment per file and review type while full history remains append-only.';

COMMIT;
