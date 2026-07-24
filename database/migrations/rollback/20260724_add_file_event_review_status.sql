BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.file_events
        WHERE event_status <> 'active'
    ) THEN
        RAISE EXCEPTION
            'Rollback blocked: reviewed file events would lose their status';
    END IF;
END;
$$;

DROP VIEW IF EXISTS public.v_file_events_effective;
ALTER TABLE public.file_events
    DROP CONSTRAINT IF EXISTS file_events_event_status_check,
    DROP COLUMN IF EXISTS review_reason,
    DROP COLUMN IF EXISTS reviewed_at,
    DROP COLUMN IF EXISTS event_status;

COMMIT;
