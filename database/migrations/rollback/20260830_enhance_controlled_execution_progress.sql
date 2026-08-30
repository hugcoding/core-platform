BEGIN;
DROP VIEW public.v_controlled_execution_batch_progress;
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
