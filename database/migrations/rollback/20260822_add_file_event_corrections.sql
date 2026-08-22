BEGIN;

CREATE OR REPLACE VIEW public.v_file_events_effective AS
SELECT * FROM public.file_events WHERE event_status <> 'invalidated';

DROP TRIGGER IF EXISTS file_event_corrections_append_only
    ON public.file_event_corrections;
DROP FUNCTION IF EXISTS public.reject_file_event_correction_mutation();
DROP TABLE IF EXISTS public.file_event_corrections;

COMMIT;
