-- SCRUM-78 rollback. Run outside a transaction block.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_metadata_file_id
    ON public.metadata USING btree (file_id);
