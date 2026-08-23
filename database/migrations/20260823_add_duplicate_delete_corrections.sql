-- SCRUM-114: preserve raw DELETE observations while excluding proven scanner repeats.
BEGIN;

ALTER TABLE public.file_event_corrections
    DROP CONSTRAINT IF EXISTS file_event_corrections_correction_type_check;
ALTER TABLE public.file_event_corrections
    ADD CONSTRAINT file_event_corrections_correction_type_check CHECK (
        correction_type IN (
            'invalidated_as_non_material',
            'duplicate_observation'
        )
    );

CREATE OR REPLACE VIEW public.v_file_events_effective AS
SELECT event.*
FROM public.file_events event
WHERE event.event_status <> 'invalidated'
  AND NOT EXISTS (
      SELECT 1
      FROM public.file_event_corrections correction
      WHERE correction.file_event_id = event.id
        AND correction.correction_type IN (
            'invalidated_as_non_material',
            'duplicate_observation'
        )
  );

COMMENT ON VIEW public.v_file_events_effective IS
    'Effective event history excluding append-only proven non-material and duplicate observations; raw file_events remain unchanged.';

COMMIT;
