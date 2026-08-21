-- Persist deterministic document-content privacy evidence without raw extracted text.
BEGIN;

CREATE TABLE IF NOT EXISTS public.file_privacy_evidence (
    id bigserial PRIMARY KEY,
    file_id bigint NOT NULL REFERENCES public.files(id) ON DELETE CASCADE,
    content_sha256 text NOT NULL,
    classification text NOT NULL CHECK (classification IN ('low', 'medium', 'high')),
    confidence text NOT NULL CHECK (confidence IN ('low', 'medium', 'high')),
    signals text[] NOT NULL DEFAULT '{}',
    rule_version text NOT NULL,
    extractor_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (file_id, content_sha256, rule_version)
);

CREATE INDEX IF NOT EXISTS file_privacy_evidence_current_content_idx
    ON public.file_privacy_evidence (file_id, content_sha256, created_at DESC, id DESC);

COMMENT ON TABLE public.file_privacy_evidence IS
    'Append-only deterministic privacy evidence for an exact file content hash; raw text is not stored.';

COMMIT;
