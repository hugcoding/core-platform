-- Persistent, content-bound OCR requests for the Workset portal.
BEGIN;

CREATE TABLE IF NOT EXISTS public.workset_ocr_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key uuid NOT NULL UNIQUE,
    file_id bigint NOT NULL REFERENCES public.files(id) ON DELETE CASCADE,
    content_sha256 text NOT NULL,
    priority smallint NOT NULL DEFAULT 100,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'ready', 'failed', 'cancelled')),
    waiting_reason text,
    engine text NOT NULL DEFAULT 'tesseract',
    engine_version text,
    languages text NOT NULL DEFAULT 'nld+eng',
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    pages integer CHECK (pages >= 0),
    characters integer CHECK (characters >= 0),
    text_sha256 text,
    artifact_path text,
    error_code text,
    requested_by text NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (status <> 'ready' OR (
        finished_at IS NOT NULL AND text_sha256 IS NOT NULL
        AND artifact_path IS NOT NULL AND characters > 0
    ))
);

CREATE UNIQUE INDEX IF NOT EXISTS workset_ocr_jobs_open_content_idx
    ON public.workset_ocr_jobs(content_sha256)
    WHERE status IN ('pending', 'running');
CREATE INDEX IF NOT EXISTS workset_ocr_jobs_claim_idx
    ON public.workset_ocr_jobs(priority DESC, requested_at, id)
    WHERE status='pending';
CREATE INDEX IF NOT EXISTS workset_ocr_jobs_ready_content_idx
    ON public.workset_ocr_jobs(content_sha256, finished_at DESC)
    WHERE status='ready';

COMMENT ON TABLE public.workset_ocr_jobs IS
    'Append-only OCR requests and metadata; source files remain unchanged and OCR text is stored as a local compressed artifact.';

COMMIT;
