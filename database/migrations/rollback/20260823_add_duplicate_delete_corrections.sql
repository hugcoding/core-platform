-- Behavioral rollback: preserve append-only correction evidence but stop applying
-- duplicate_observation corrections to effective history.
BEGIN;

CREATE OR REPLACE VIEW public.v_file_events_effective AS
SELECT event.*
FROM public.file_events event
WHERE event.event_status <> 'invalidated'
  AND NOT EXISTS (
      SELECT 1
      FROM public.file_event_corrections correction
      WHERE correction.file_event_id = event.id
        AND correction.correction_type = 'invalidated_as_non_material'
  );

COMMENT ON VIEW public.v_file_events_effective IS
    'Effective event history excluding append-only proven non-material observations; duplicate-observation evidence is preserved but inactive after rollback.';

COMMIT;
