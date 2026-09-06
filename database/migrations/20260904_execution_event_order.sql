-- Preserve history; repair ambiguous planned/queued ties without replaying batches.
BEGIN;
SET LOCAL lock_timeout='2s';
ALTER TABLE public.controlled_execution_events
  ADD COLUMN IF NOT EXISTS event_order bigint GENERATED ALWAYS AS IDENTITY;
ALTER TABLE public.controlled_execution_events ALTER COLUMN created_at SET DEFAULT clock_timestamp();
CREATE INDEX IF NOT EXISTS controlled_execution_events_item_order_idx
  ON public.controlled_execution_events(item_id, created_at DESC,
    (CASE event_type WHEN 'planned' THEN 0 WHEN 'queued' THEN 1 ELSE 2 END) DESC, event_order DESC);
CREATE INDEX IF NOT EXISTS controlled_execution_events_batch_order_idx
  ON public.controlled_execution_events(batch_id, created_at DESC, event_order DESC)
  WHERE item_id IS NULL;
CREATE OR REPLACE VIEW public.v_controlled_execution_item_status AS
SELECT item.*, latest.event_type AS current_status, latest.details AS latest_details,
       latest.created_at AS status_changed_at
FROM public.controlled_execution_batch_items item
LEFT JOIN LATERAL (
  SELECT event_type, details, created_at FROM public.controlled_execution_events event
  WHERE event.item_id=item.id
  ORDER BY event.created_at DESC,
    CASE event_type WHEN 'planned' THEN 0 WHEN 'queued' THEN 1 ELSE 2 END DESC,
    event.event_order DESC LIMIT 1
) latest ON true;
CREATE OR REPLACE VIEW public.v_controlled_execution_batch_progress AS
SELECT batch.id, batch.item_count, latest.event_type AS batch_status,
  count(*) FILTER (WHERE status.current_status IN ('verified','completed','event_correlated')) AS succeeded,
  count(*) FILTER (WHERE status.current_status = 'blocked') AS blocked,
  count(*) FILTER (WHERE status.current_status = 'failed') AS failed,
  count(*) FILTER (WHERE status.current_status IN ('planned','approved','queued','started')) AS pending,
  count(*) FILTER (WHERE status.current_status = 'rolled_back') AS rolled_back,
  batch.created_at
FROM public.controlled_execution_batches batch
JOIN public.v_controlled_execution_item_status status ON status.batch_id=batch.id
LEFT JOIN LATERAL (
  SELECT event_type FROM public.controlled_execution_events event
  WHERE event.batch_id=batch.id AND event.item_id IS NULL
  ORDER BY event.created_at DESC, event.event_order DESC LIMIT 1
) latest ON true
GROUP BY batch.id,batch.item_count,latest.event_type,batch.created_at;
COMMIT;
