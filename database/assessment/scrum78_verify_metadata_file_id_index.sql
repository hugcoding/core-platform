\echo '=== SCRUM-78 metadata file_id indexes ==='
SELECT
    psi.indexrelname AS index_name,
    pg_size_pretty(pg_relation_size(psi.indexrelid)) AS size,
    psi.idx_scan,
    pi.indexdef
FROM pg_stat_user_indexes psi
JOIN pg_indexes pi
  ON pi.schemaname = psi.schemaname
 AND pi.tablename = psi.relname
 AND pi.indexname = psi.indexrelname
WHERE psi.relname = 'metadata'
  AND psi.indexrelname IN ('metadata_file_id_unique', 'idx_metadata_file_id')
ORDER BY psi.indexrelname;

\echo '=== Representative file_id lookup ==='
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM public.metadata
WHERE file_id = (
    SELECT file_id
    FROM public.metadata
    LIMIT 1
);
