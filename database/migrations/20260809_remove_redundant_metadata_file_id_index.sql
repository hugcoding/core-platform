-- SCRUM-78: metadata_file_id_unique already supports ordinary file_id lookups.
-- PostgreSQL does not allow DROP INDEX CONCURRENTLY inside a transaction block.
DROP INDEX CONCURRENTLY IF EXISTS public.idx_metadata_file_id;
