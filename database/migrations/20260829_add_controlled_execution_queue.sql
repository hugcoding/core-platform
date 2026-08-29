-- SCRUM-116: immutable approval batches with append-only execution progress.
BEGIN;
CREATE TABLE IF NOT EXISTS public.controlled_execution_batches (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  contract_version text NOT NULL,
  batch_key text NOT NULL UNIQUE CHECK (batch_key ~ '^[0-9a-f]{64}$'),
  item_count integer NOT NULL CHECK (item_count BETWEEN 1 AND 25),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.controlled_execution_batch_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id uuid NOT NULL REFERENCES public.controlled_execution_batches(id) ON DELETE RESTRICT,
  sequence_no integer NOT NULL CHECK (sequence_no BETWEEN 1 AND 25),
  action_type text NOT NULL CHECK (action_type IN (
    'quarantine_exact_duplicate','quarantine_content_similar','quarantine_deletion_review',
    'migrate_active','migrate_inactive'
  )),
  priority integer NOT NULL CHECK (priority BETWEEN 10 AND 50),
  file_id bigint NOT NULL REFERENCES public.files(id) ON DELETE RESTRICT,
  source_path text NOT NULL CHECK (source_path LIKE '/volume1/data/%'),
  target_path text NOT NULL CHECK (target_path LIKE '/volume1/data/%' AND target_path <> source_path),
  content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  size_bytes bigint NOT NULL CHECK (size_bytes > 0),
  evidence_snapshot jsonb NOT NULL CHECK (jsonb_typeof(evidence_snapshot) = 'object'),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(batch_id, sequence_no), UNIQUE(batch_id, file_id), UNIQUE(batch_id, target_path)
);
CREATE TABLE IF NOT EXISTS public.controlled_execution_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id uuid NOT NULL REFERENCES public.controlled_execution_batches(id) ON DELETE RESTRICT,
  item_id uuid REFERENCES public.controlled_execution_batch_items(id) ON DELETE RESTRICT,
  event_type text NOT NULL CHECK (event_type IN (
    'planned','approved','queued','started','verified','blocked','failed','completed',
    'event_correlated','rollback_pending','rolled_back','paused'
  )),
  idempotency_key text NOT NULL UNIQUE,
  actor text NOT NULL,
  details jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(details) = 'object'),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE OR REPLACE FUNCTION public.reject_controlled_execution_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  RAISE EXCEPTION 'controlled execution data is append-only';
END $$;
CREATE TRIGGER controlled_execution_batches_immutable BEFORE UPDATE OR DELETE ON public.controlled_execution_batches
FOR EACH ROW EXECUTE FUNCTION public.reject_controlled_execution_mutation();
CREATE TRIGGER controlled_execution_items_immutable BEFORE UPDATE OR DELETE ON public.controlled_execution_batch_items
FOR EACH ROW EXECUTE FUNCTION public.reject_controlled_execution_mutation();
CREATE TRIGGER controlled_execution_events_immutable BEFORE UPDATE OR DELETE ON public.controlled_execution_events
FOR EACH ROW EXECUTE FUNCTION public.reject_controlled_execution_mutation();
CREATE OR REPLACE VIEW public.v_controlled_execution_item_status AS
SELECT item.*, latest.event_type AS current_status, latest.details AS latest_details,
       latest.created_at AS status_changed_at
FROM public.controlled_execution_batch_items item
LEFT JOIN LATERAL (
  SELECT event_type, details, created_at FROM public.controlled_execution_events event
  WHERE event.item_id = item.id ORDER BY event.created_at DESC, event.id DESC LIMIT 1
) latest ON true;
CREATE OR REPLACE VIEW public.v_controlled_execution_batch_progress AS
SELECT batch.id, batch.item_count, latest.event_type AS batch_status,
  count(*) FILTER (WHERE status.current_status IN ('verified','completed','event_correlated')) AS succeeded,
  count(*) FILTER (WHERE status.current_status = 'blocked') AS blocked,
  count(*) FILTER (WHERE status.current_status = 'failed') AS failed,
  count(*) FILTER (WHERE status.current_status IN ('planned','approved','queued','started')) AS pending
FROM public.controlled_execution_batches batch
JOIN public.v_controlled_execution_item_status status ON status.batch_id = batch.id
LEFT JOIN LATERAL (
  SELECT event_type FROM public.controlled_execution_events event
  WHERE event.batch_id = batch.id AND event.item_id IS NULL
  ORDER BY event.created_at DESC, event.id DESC LIMIT 1
) latest ON true
GROUP BY batch.id, batch.item_count, latest.event_type;
COMMIT;
