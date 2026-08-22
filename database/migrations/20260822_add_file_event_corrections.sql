BEGIN;

CREATE TABLE IF NOT EXISTS public.file_event_corrections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    file_event_id uuid NOT NULL REFERENCES public.file_events(id) ON DELETE RESTRICT,
    correction_type text NOT NULL CHECK (
        correction_type IN ('invalidated_as_non_material')
    ),
    reason text NOT NULL,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (file_event_id, correction_type)
);

CREATE OR REPLACE FUNCTION public.reject_file_event_correction_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'file_event_corrections is append-only';
END;
$$;

DROP TRIGGER IF EXISTS file_event_corrections_append_only
    ON public.file_event_corrections;
CREATE TRIGGER file_event_corrections_append_only
BEFORE UPDATE OR DELETE ON public.file_event_corrections
FOR EACH ROW EXECUTE FUNCTION public.reject_file_event_correction_mutation();

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

COMMENT ON TABLE public.file_event_corrections IS
    'Append-only corrections that preserve original file events while excluding proven false mutations from effective history.';

COMMIT;
