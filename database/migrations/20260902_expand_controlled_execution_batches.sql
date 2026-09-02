-- Increase the approval limit without changing existing batches or evidence.
BEGIN;
ALTER TABLE public.controlled_execution_batches
  DROP CONSTRAINT controlled_execution_batches_item_count_check;
ALTER TABLE public.controlled_execution_batches
  ADD CONSTRAINT controlled_execution_batches_item_count_check
  CHECK (item_count BETWEEN 1 AND 50);
ALTER TABLE public.controlled_execution_batch_items
  DROP CONSTRAINT controlled_execution_batch_items_sequence_no_check;
ALTER TABLE public.controlled_execution_batch_items
  ADD CONSTRAINT controlled_execution_batch_items_sequence_no_check
  CHECK (sequence_no BETWEEN 1 AND 50);
COMMIT;
