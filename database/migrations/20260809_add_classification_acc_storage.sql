BEGIN;

CREATE TABLE IF NOT EXISTS public.classification_runs (
    id uuid PRIMARY KEY,
    environment text NOT NULL CHECK (environment = 'acceptance'),
    manifest_sha256 text NOT NULL,
    prompt_version text NOT NULL,
    contract_version text NOT NULL,
    provider_id text NOT NULL,
    model_id text NOT NULL,
    status text NOT NULL CHECK (status IN ('completed', 'completed_with_errors')),
    document_count integer NOT NULL CHECK (document_count >= 0),
    proposal_count integer NOT NULL CHECK (proposal_count >= 0),
    error_count integer NOT NULL CHECK (error_count >= 0),
    classification_seconds numeric CHECK (classification_seconds >= 0),
    prompt_tokens bigint CHECK (prompt_tokens >= 0),
    completion_tokens bigint CHECK (completion_tokens >= 0),
    total_tokens bigint CHECK (total_tokens >= 0),
    local_provider boolean NOT NULL DEFAULT true CHECK (local_provider = true),
    raw_text_stored boolean NOT NULL DEFAULT false CHECK (raw_text_stored = false),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (manifest_sha256, prompt_version, contract_version, provider_id, model_id)
);

CREATE TABLE IF NOT EXISTS public.classification_proposals (
    id uuid PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES public.classification_runs(id) ON DELETE CASCADE,
    file_id integer NOT NULL REFERENCES public.files(id) ON DELETE CASCADE,
    content_group_id uuid REFERENCES public.content_groups(id) ON DELETE SET NULL,
    content_sha256 text NOT NULL,
    classifier_key text NOT NULL,
    proposal_sha256 text NOT NULL,
    status text NOT NULL DEFAULT 'pending_review'
        CHECK (status IN ('pending_review')),
    document_type text NOT NULL,
    model_category text NOT NULL,
    category text NOT NULL CHECK (category IN
        ('personal', 'administration', 'finance', 'home', 'work', 'study', 'projects', 'other')),
    model_document_family text NOT NULL,
    document_family text NOT NULL,
    topics text[] NOT NULL DEFAULT '{}',
    lifecycle text NOT NULL CHECK (lifecycle IN
        ('active_candidate', 'archive_candidate', 'needs_review', 'quarantine')),
    suggested_path text NOT NULL,
    model_sensitivity text NOT NULL,
    sensitivity text NOT NULL CHECK (sensitivity IN
        ('normal', 'personal', 'sensitive', 'highly_sensitive')),
    sensitivity_signals text[] NOT NULL DEFAULT '{}',
    model_confidence text NOT NULL,
    confidence text NOT NULL CHECK (confidence IN ('low', 'medium', 'high')),
    normalization_warnings text[] NOT NULL DEFAULT '{}',
    reason text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, file_id)
);

CREATE INDEX IF NOT EXISTS idx_classification_proposals_file
    ON public.classification_proposals(file_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_classification_proposals_classifier
    ON public.classification_proposals(classifier_key, content_sha256);

CREATE TABLE IF NOT EXISTS public.classification_reviews (
    id uuid PRIMARY KEY,
    proposal_id uuid NOT NULL REFERENCES public.classification_proposals(id) ON DELETE CASCADE,
    idempotency_key text NOT NULL UNIQUE,
    review_sha256 text NOT NULL,
    decision text NOT NULL CHECK (decision IN ('accepted', 'rejected')),
    reviewer text NOT NULL,
    reviewed_at timestamptz NOT NULL,
    category text CHECK (category IN
        ('personal', 'administration', 'finance', 'home', 'work', 'study', 'projects', 'other')),
    document_family text,
    lifecycle text CHECK (lifecycle IN
        ('active_candidate', 'archive_candidate', 'needs_review', 'quarantine')),
    suggested_path text,
    sensitivity text CHECK (sensitivity IN
        ('normal', 'personal', 'sensitive', 'highly_sensitive')),
    confidence text CHECK (confidence IN ('low', 'medium', 'high')),
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (decision = 'rejected' OR
        (category IS NOT NULL AND document_family IS NOT NULL AND lifecycle IS NOT NULL
         AND suggested_path IS NOT NULL AND sensitivity IS NOT NULL AND confidence IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_classification_reviews_proposal
    ON public.classification_reviews(proposal_id, reviewed_at DESC, created_at DESC);

CREATE OR REPLACE VIEW public.v_current_file_classification AS
WITH latest_review AS (
    SELECT DISTINCT ON (proposal_id) *
    FROM public.classification_reviews
    ORDER BY proposal_id, reviewed_at DESC, created_at DESC, id DESC
), accepted_current AS (
SELECT DISTINCT ON (p.file_id)
    p.file_id,
    p.content_group_id,
    p.content_sha256,
    p.id AS proposal_id,
    p.run_id,
    r.id AS review_id,
    r.reviewer,
    r.reviewed_at,
    p.document_type,
    r.category,
    r.document_family,
    p.topics,
    r.lifecycle,
    r.suggested_path,
    r.sensitivity,
    r.confidence,
    p.reason,
    p.normalization_warnings,
    cr.provider_id,
    cr.model_id,
    cr.prompt_version,
    cr.contract_version,
    p.created_at AS proposed_at
FROM public.classification_proposals p
JOIN latest_review r ON r.proposal_id = p.id AND r.decision = 'accepted'
JOIN public.classification_runs cr ON cr.id = p.run_id
JOIN public.files f ON f.id = p.file_id
JOIN public.content_groups cg ON cg.id = p.content_group_id
WHERE f.deleted_at IS NULL
  AND cg.golden_file_id = f.id
  AND f.content_sha256 = p.content_sha256
ORDER BY p.file_id, r.reviewed_at DESC, p.created_at DESC, p.id DESC
)
SELECT * FROM accepted_current;

COMMENT ON VIEW public.v_current_file_classification IS
    'Newest accepted, human-reviewed classification per current golden proposal; stale hashes and non-golden files are excluded.';

COMMIT;
