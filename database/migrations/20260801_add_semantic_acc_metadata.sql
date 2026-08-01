BEGIN;

CREATE TABLE IF NOT EXISTS public.semantic_runs (
    id uuid PRIMARY KEY,
    environment text NOT NULL CHECK (environment IN ('acceptance')),
    manifest_sha256 text NOT NULL,
    source text NOT NULL,
    selection_version text NOT NULL,
    extractor_version text NOT NULL,
    chunker_version text NOT NULL,
    status text NOT NULL CHECK (status IN ('completed', 'completed_with_errors')),
    document_count integer NOT NULL CHECK (document_count >= 0),
    chunk_count integer NOT NULL CHECK (chunk_count >= 0),
    error_count integer NOT NULL CHECK (error_count >= 0),
    embedding_enabled boolean NOT NULL DEFAULT false CHECK (embedding_enabled = false),
    external_ai_enabled boolean NOT NULL DEFAULT false CHECK (external_ai_enabled = false),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (manifest_sha256, extractor_version, chunker_version)
);

CREATE TABLE IF NOT EXISTS public.semantic_documents (
    run_id uuid NOT NULL REFERENCES public.semantic_runs(id) ON DELETE CASCADE,
    file_id integer NOT NULL REFERENCES public.files(id) ON DELETE CASCADE,
    content_group_id uuid REFERENCES public.content_groups(id) ON DELETE SET NULL,
    content_sha256 text NOT NULL,
    status text NOT NULL CHECK (status IN ('planned', 'needs_ocr', 'no_text', 'password_protected', 'error', 'skipped')),
    extension text,
    size_bytes bigint CHECK (size_bytes >= 0),
    characters integer CHECK (characters >= 0),
    words integer CHECK (words >= 0),
    pages integer CHECK (pages >= 0),
    estimated_tokens integer CHECK (estimated_tokens >= 0),
    chunk_count integer NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
    error_type text,
    error_reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, file_id)
);

CREATE TABLE IF NOT EXISTS public.semantic_chunks (
    run_id uuid NOT NULL,
    file_id integer NOT NULL,
    chunk_id text NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    content_sha256 text NOT NULL,
    words integer NOT NULL CHECK (words > 0),
    characters integer NOT NULL CHECK (characters > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, chunk_id),
    UNIQUE (run_id, file_id, ordinal),
    FOREIGN KEY (run_id, file_id) REFERENCES public.semantic_documents(run_id, file_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_semantic_documents_file_id ON public.semantic_documents(file_id);
CREATE INDEX IF NOT EXISTS idx_semantic_chunks_file_id ON public.semantic_chunks(file_id);

COMMIT;
