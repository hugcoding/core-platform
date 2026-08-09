\pset pager off

-- SCRUM-78 read-only database growth and overlap baseline.
-- This assessment contains SELECT statements only.

SELECT
    now() AS measured_at,
    current_database() AS database,
    pg_database_size(current_database()) AS database_bytes,
    pg_size_pretty(pg_database_size(current_database())) AS database_size;

SELECT
    relname AS table_name,
    n_live_tup AS estimated_rows,
    n_dead_tup AS dead_rows,
    pg_total_relation_size(relid) AS total_bytes,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
    pg_size_pretty(pg_relation_size(relid)) AS table_size,
    pg_size_pretty(pg_indexes_size(relid)) AS indexes_size,
    last_autoanalyze,
    last_autovacuum
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC;

SELECT
    tables.relname AS table_name,
    indexes.relname AS index_name,
    pg_relation_size(indexes.oid) AS index_bytes,
    pg_size_pretty(pg_relation_size(indexes.oid)) AS index_size,
    stats.idx_scan,
    pg_get_indexdef(indexes.oid) AS definition
FROM pg_stat_user_indexes stats
JOIN pg_class tables ON tables.oid = stats.relid
JOIN pg_class indexes ON indexes.oid = stats.indexrelid
ORDER BY pg_relation_size(indexes.oid) DESC;

SELECT 'files' AS entity, count(*) AS rows FROM public.files
UNION ALL SELECT 'metadata', count(*) FROM public.metadata
UNION ALL SELECT 'file_events', count(*) FROM public.file_events
UNION ALL SELECT 'folders', count(*) FROM public.folders
UNION ALL SELECT 'content_groups', count(*) FROM public.content_groups
UNION ALL SELECT 'content_group_members', count(*) FROM public.content_group_members
UNION ALL SELECT 'scan_sessions', count(*) FROM public.scan_sessions
UNION ALL SELECT 'semantic_runs', count(*) FROM public.semantic_runs
UNION ALL SELECT 'semantic_documents', count(*) FROM public.semantic_documents
UNION ALL SELECT 'semantic_chunks', count(*) FROM public.semantic_chunks
UNION ALL SELECT 'semantic_embedding_runs', count(*) FROM public.semantic_embedding_runs
UNION ALL SELECT 'semantic_embeddings_acc', count(*) FROM public.semantic_embeddings_acc
UNION ALL SELECT 'classification_runs', count(*) FROM public.classification_runs
UNION ALL SELECT 'classification_proposals', count(*) FROM public.classification_proposals
UNION ALL SELECT 'classification_reviews', count(*) FROM public.classification_reviews
ORDER BY entity;

SELECT
    count(*) FILTER (WHERE deleted_at IS NULL) AS active_files,
    count(*) FILTER (WHERE deleted_at IS NOT NULL) AS deleted_files,
    count(*) FILTER (WHERE size_bytes = 0 AND deleted_at IS NULL) AS active_empty,
    count(*) FILTER (
        WHERE content_sha256 IS NULL AND deleted_at IS NULL
    ) AS active_without_full_hash
FROM public.files;

SELECT
    event_type,
    count(*) AS rows,
    min(created_at) AS oldest,
    max(created_at) AS newest
FROM public.file_events
GROUP BY event_type
ORDER BY rows DESC;

SELECT
    type,
    count(*) AS sessions,
    min(started_at) AS oldest,
    max(started_at) AS newest
FROM public.scan_sessions
GROUP BY type
ORDER BY sessions DESC;

SELECT
    count(*) AS rows,
    count(*) FILTER (WHERE width IS NULL) AS width_null,
    count(*) FILTER (WHERE height IS NULL) AS height_null,
    count(*) FILTER (WHERE duration IS NULL) AS duration_null,
    count(*) FILTER (WHERE missing IS TRUE) AS missing_true
FROM public.metadata;
