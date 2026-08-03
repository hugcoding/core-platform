BEGIN;

CREATE TABLE IF NOT EXISTS public.semantic_embedding_runs (
    id uuid PRIMARY KEY,
    semantic_run_id uuid NOT NULL REFERENCES public.semantic_runs(id) ON DELETE CASCADE,
    environment text NOT NULL CHECK (environment = 'acceptance'),
    model_id text NOT NULL,
    model_revision text NOT NULL,
    dimension integer NOT NULL CHECK (dimension > 0),
    chunker_version text NOT NULL,
    batch_size integer NOT NULL CHECK (batch_size > 0),
    status text NOT NULL CHECK (status IN ('completed', 'completed_with_errors')),
    document_count integer NOT NULL CHECK (document_count >= 0),
    chunk_count integer NOT NULL CHECK (chunk_count >= 0),
    error_count integer NOT NULL CHECK (error_count >= 0),
    network_enabled boolean NOT NULL DEFAULT false CHECK (network_enabled = false),
    raw_text_stored boolean NOT NULL DEFAULT false CHECK (raw_text_stored = false),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (semantic_run_id, model_id, model_revision, chunker_version)
);

CREATE TABLE IF NOT EXISTS public.semantic_embeddings_acc (
    embedding_run_id uuid NOT NULL REFERENCES public.semantic_embedding_runs(id) ON DELETE CASCADE,
    semantic_run_id uuid NOT NULL,
    file_id integer NOT NULL,
    chunk_id text NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    content_sha256 text NOT NULL,
    token_count integer NOT NULL CHECK (token_count > 0),
    embedding vector(384) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (embedding_run_id, chunk_id),
    UNIQUE (embedding_run_id, file_id, ordinal),
    FOREIGN KEY (semantic_run_id, file_id)
        REFERENCES public.semantic_documents(run_id, file_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_semantic_embeddings_acc_file
    ON public.semantic_embeddings_acc(file_id);

COMMIT;
