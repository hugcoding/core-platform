BEGIN;

CREATE TABLE IF NOT EXISTS public.file_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id integer NULL REFERENCES public.files(id) ON DELETE SET NULL,
    candidate_file_id integer NULL REFERENCES public.files(id) ON DELETE SET NULL,
    event_type text NOT NULL,
    old_path text NULL,
    new_path text NULL,
    content_version bigint NULL,
    confidence_score numeric(5,2) NULL,
    confidence_level text NULL,
    decision text NULL,
    signals jsonb NOT NULL DEFAULT '{}'::jsonb,
    reason text NULL,
    scan_session_id uuid NULL,
    source text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT file_events_confidence_level_check
        CHECK (confidence_level IS NULL OR confidence_level IN ('high', 'medium', 'low', 'ambiguous'))
);

CREATE INDEX IF NOT EXISTS file_events_file_created_idx
    ON public.file_events (file_id, created_at DESC);
CREATE INDEX IF NOT EXISTS file_events_type_created_idx
    ON public.file_events (event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS file_events_review_idx
    ON public.file_events (confidence_level, created_at DESC)
    WHERE confidence_level IN ('medium', 'low', 'ambiguous');

COMMENT ON TABLE public.file_events IS
    'Append-only audit log for file mutations, identity decisions and integrity signals.';

COMMIT;
