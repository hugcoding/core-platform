-- Bounded automatic discovery reuses proposals and does not retry abstentions forever.
BEGIN;
SET LOCAL lock_timeout = '2s';
CREATE INDEX IF NOT EXISTS workset_ai_jobs_content_attempt_idx
ON public.workset_ai_jobs(file_id, content_sha256, model_id, prompt_version);
CREATE INDEX IF NOT EXISTS workset_ai_jobs_proposal_idx
ON public.workset_ai_jobs(proposal_id) WHERE proposal_id IS NOT NULL;
COMMIT;
