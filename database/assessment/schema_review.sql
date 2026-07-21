\pset pager off

-- SCRUM-53: read-only database schema review.
-- This script only executes SELECT statements.

SELECT
    c.table_name,
    c.ordinal_position,
    c.column_name,
    c.data_type,
    c.is_nullable,
    c.column_default,
    s.null_frac,
    s.n_distinct
FROM information_schema.columns c
LEFT JOIN pg_stats s
    ON s.schemaname = c.table_schema
   AND s.tablename = c.table_name
   AND s.attname = c.column_name
WHERE c.table_schema = 'public'
ORDER BY c.table_name, c.ordinal_position;

SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_analyze,
    last_autoanalyze,
    n_tup_ins,
    n_tup_upd,
    n_tup_del
FROM pg_stat_user_tables
ORDER BY relname;

SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;

SELECT
    conrelid::regclass AS table_name,
    conname,
    contype,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE connamespace = 'public'::regnamespace
ORDER BY conrelid::regclass::text, conname;

SELECT viewname, definition
FROM pg_views
WHERE schemaname = 'public'
ORDER BY viewname;

SELECT
    count(*) AS files_total,
    count(*) FILTER (WHERE xxhash IS NULL) AS xxhash_null,
    count(*) FILTER (WHERE hash_path IS NULL) AS hash_path_null,
    count(*) FILTER (WHERE xxhash IS NOT DISTINCT FROM hash_path) AS xxhash_equals_hash_path,
    count(*) FILTER (WHERE mime_type IS NULL) AS mime_null,
    count(*) FILTER (WHERE path IS NULL) AS path_null,
    count(*) FILTER (WHERE deleted_at IS NOT NULL) AS deleted_rows,
    count(*) FILTER (WHERE last_mutation_at IS NOT NULL) AS mutation_tracked
FROM public.files;

SELECT
    count(*) AS metadata_total,
    count(*) FILTER (WHERE duration IS NULL) AS duration_null,
    count(*) FILTER (WHERE mime_type IS NULL) AS mime_null,
    count(*) FILTER (WHERE missing) AS marked_missing
FROM public.metadata;

SELECT count(*) AS mime_disagreements
FROM public.files f
JOIN public.metadata m ON m.file_id = f.id
WHERE f.mime_type IS DISTINCT FROM m.mime_type;

SELECT source, count(*)
FROM public.files
GROUP BY source
ORDER BY count(*) DESC;

SELECT last_mutation_type, count(*)
FROM public.files
GROUP BY last_mutation_type
ORDER BY count(*) DESC;

