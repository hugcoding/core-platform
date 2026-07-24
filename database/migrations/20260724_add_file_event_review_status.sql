BEGIN;

ALTER TABLE public.file_events
    ADD COLUMN IF NOT EXISTS event_status text NOT NULL DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS reviewed_at timestamptz NULL,
    ADD COLUMN IF NOT EXISTS review_reason text NULL;

ALTER TABLE public.file_events
    DROP CONSTRAINT IF EXISTS file_events_event_status_check;
ALTER TABLE public.file_events
    ADD CONSTRAINT file_events_event_status_check
    CHECK (event_status IN ('active', 'confirmed', 'invalidated'));

CREATE OR REPLACE VIEW public.v_file_events_effective AS
SELECT *
FROM public.file_events
WHERE event_status <> 'invalidated';

COMMIT;
