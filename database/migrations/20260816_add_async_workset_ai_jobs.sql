-- SCRUM-106: persistent, single-document, resource-aware AI queue.
BEGIN;

CREATE TABLE IF NOT EXISTS public.workset_ai_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key uuid NOT NULL UNIQUE,
    file_id bigint NOT NULL REFERENCES public.files(id) ON DELETE CASCADE,
    content_sha256 text NOT NULL,
    workset_status_snapshot text NOT NULL
        CHECK (workset_status_snapshot IN ('active', 'needs_review', 'inactive')),
    priority smallint NOT NULL CHECK (priority IN (100, 200, 300)),
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'ready', 'failed', 'abstained', 'cancelled')),
    waiting_reason text,
    provider_id text NOT NULL DEFAULT 'openai-compatible-local',
    model_id text NOT NULL,
    prompt_version text NOT NULL,
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    run_id uuid REFERENCES public.workset_ai_runs(id),
    proposal_id uuid REFERENCES public.workset_ai_proposals(id),
    error_code text,
    requested_by text NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (status <> 'running' OR (started_at IS NOT NULL AND finished_at IS NULL)),
    CHECK (status NOT IN ('ready', 'abstained', 'failed', 'cancelled') OR finished_at IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS workset_ai_jobs_open_file_model_prompt_idx
    ON public.workset_ai_jobs(file_id, model_id, prompt_version)
    WHERE status IN ('pending', 'running');
CREATE INDEX IF NOT EXISTS workset_ai_jobs_claim_idx
    ON public.workset_ai_jobs(priority DESC, requested_at, id)
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS workset_ai_jobs_ready_idx
    ON public.workset_ai_jobs(finished_at DESC, id)
    WHERE status = 'ready';

CREATE OR REPLACE VIEW public.v_workset_ai_job_summary AS
SELECT status, count(*)::bigint AS job_count,
       min(requested_at) AS oldest_requested_at,
       max(updated_at) AS latest_updated_at
FROM public.workset_ai_jobs
GROUP BY status;

CREATE OR REPLACE VIEW public.v_latest_workset_ai_job AS
SELECT DISTINCT ON (j.file_id)
    j.id, j.file_id, j.content_sha256, j.workset_status_snapshot,
    j.priority, j.status, j.waiting_reason, j.provider_id, j.model_id,
    j.prompt_version, j.attempt_count, j.run_id, j.proposal_id,
    j.error_code, j.requested_by, j.requested_at, j.started_at,
    j.finished_at, j.updated_at
FROM public.workset_ai_jobs j
JOIN public.files f ON f.id = j.file_id AND f.deleted_at IS NULL
ORDER BY j.file_id, j.requested_at DESC, j.id DESC;

COMMENT ON TABLE public.workset_ai_jobs IS
    'Persistent individual workset AI requests; proposals remain advice until human review.';

COMMIT;
