-- SCRUM-101: local LLM advice for at most five explicitly selected documents.
BEGIN;

CREATE TABLE IF NOT EXISTS public.workset_ai_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key text NOT NULL UNIQUE,
    channel text NOT NULL CHECK (channel = 'workset_portal'),
    status text NOT NULL CHECK (status IN ('completed', 'completed_with_errors')),
    selected_file_ids bigint[] NOT NULL CHECK (cardinality(selected_file_ids) BETWEEN 1 AND 5),
    selection_snapshot jsonb NOT NULL CHECK (jsonb_typeof(selection_snapshot) = 'object'),
    provider_id text NOT NULL,
    model_id text NOT NULL,
    prompt_version text NOT NULL,
    schema_version text NOT NULL,
    document_count integer NOT NULL CHECK (document_count BETWEEN 1 AND 5),
    proposal_count integer NOT NULL CHECK (proposal_count BETWEEN 0 AND 5),
    error_count integer NOT NULL CHECK (error_count BETWEEN 0 AND 5),
    prompt_tokens bigint CHECK (prompt_tokens >= 0),
    completion_tokens bigint CHECK (completion_tokens >= 0),
    total_tokens bigint CHECK (total_tokens >= 0),
    duration_seconds numeric CHECK (duration_seconds >= 0),
    local_provider boolean NOT NULL DEFAULT true CHECK (local_provider = true),
    raw_text_stored boolean NOT NULL DEFAULT false CHECK (raw_text_stored = false),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.workset_ai_proposals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES public.workset_ai_runs(id) ON DELETE CASCADE,
    file_id bigint NOT NULL REFERENCES public.files(id) ON DELETE CASCADE,
    content_sha256 text NOT NULL,
    status text NOT NULL CHECK (status IN ('ready', 'abstained')),
    category_code text,
    family_code text,
    lifecycle text CHECK (lifecycle IN ('active', 'archive', 'needs_review')),
    privacy_advice text CHECK (privacy_advice IN ('low', 'medium', 'high')),
    confidence text NOT NULL CHECK (confidence IN ('low', 'medium', 'high')),
    relation_kind text NOT NULL CHECK (relation_kind IN
        ('none', 'source_document', 'exported_representation', 'version', 'related_document')),
    related_file_ids bigint[] NOT NULL DEFAULT '{}',
    reason text NOT NULL,
    example_review_ids uuid[] NOT NULL DEFAULT '{}',
    extraction_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, file_id),
    CHECK ((status = 'ready' AND category_code IS NOT NULL AND family_code IS NOT NULL
            AND privacy_advice IS NOT NULL)
        OR (status = 'abstained' AND category_code IS NULL AND family_code IS NULL))
);

CREATE INDEX IF NOT EXISTS workset_ai_proposals_file_idx
    ON public.workset_ai_proposals(file_id, created_at DESC);

ALTER TABLE public.document_review_events
    ADD COLUMN IF NOT EXISTS ai_proposal_id uuid REFERENCES public.workset_ai_proposals(id);

CREATE OR REPLACE VIEW public.v_latest_workset_ai_proposal AS
SELECT DISTINCT ON (p.file_id)
    p.id, p.run_id, p.file_id, p.content_sha256, p.status,
    p.category_code, p.family_code, p.lifecycle, p.privacy_advice,
    p.confidence, p.relation_kind, p.related_file_ids, p.reason,
    p.example_review_ids, p.extraction_metadata, p.created_at,
    r.provider_id, r.model_id, r.prompt_version
FROM public.workset_ai_proposals p
JOIN public.workset_ai_runs r ON r.id = p.run_id
JOIN public.files f ON f.id = p.file_id AND f.deleted_at IS NULL
JOIN public.content_groups cg ON cg.golden_file_id = f.id
WHERE f.content_sha256 = p.content_sha256
ORDER BY p.file_id, p.created_at DESC, p.id DESC;

CREATE OR REPLACE VIEW public.v_latest_document_review AS
SELECT DISTINCT ON (file_id, review_type)
    id, review_contract_version, channel, review_type, file_id,
    content_group_id, content_sha256, proposal_category_code,
    proposal_document_family_code, proposal_lifecycle, proposal_target_path,
    proposal_confidence, proposal_reason_code, decision,
    corrected_document_family_code, review_notes, reviewer,
    supersedes_event_id, created_at, proposed_category_label,
    proposed_family_label, proposed_target_path, corrected_category_code,
    proposed_target_path_raw, proposal_privacy_classification,
    corrected_privacy_classification, privacy_rule_version, privacy_evidence,
    target_path_input_kind, target_path_suggestion, target_path_suggestion_decision,
    batch_id, proposal_evidence, ai_proposal_id
FROM public.document_review_events
ORDER BY file_id, review_type, created_at DESC, id DESC;

COMMENT ON TABLE public.workset_ai_runs IS
    'Audit record for an explicit, local-only workset AI request of at most five files.';
COMMENT ON TABLE public.workset_ai_proposals IS
    'AI advice only; never a human judgment and never permission to mutate a file.';
COMMENT ON COLUMN public.document_review_events.ai_proposal_id IS
    'Optional lineage to the AI advice; corrected human values remain in this review event.';

COMMIT;
