\pset pager off

SELECT table_name, column_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND (
      (table_name = 'files' AND column_name = 'xxhash')
      OR (table_name = 'metadata' AND column_name = 'mime_type')
  );

SELECT tablename, indexname
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname IN ('idx_files_xxhash', 'idx_metadata_mime_type');

SELECT count(*) AS files_total,
       count(*) FILTER (WHERE hash_path IS NULL OR hash_path = '') AS missing_hash_path,
       count(*) FILTER (WHERE hash_content IS NULL OR hash_content = '') AS missing_hash_content,
       count(*) FILTER (WHERE mime_type IS NULL OR mime_type = '') AS missing_mime_type
FROM public.files;

SELECT count(*) AS metadata_total,
       count(*) FILTER (WHERE missing) AS marked_missing
FROM public.metadata;

SELECT count(*) AS test_documents_view_rows
FROM public.v_test_documents;
