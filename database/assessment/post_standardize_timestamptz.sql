-- Must return zero rows after 20260724_standardize_timestamptz.sql.
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN (
      'ai_output', 'embeddings', 'files', 'folders', 'metadata', 'scan_sessions'
  )
  AND data_type = 'timestamp without time zone'
ORDER BY table_name, ordinal_position;

-- Human-readable verification without changing stored values.
SELECT
    current_setting('TimeZone') AS session_timezone,
    min(created_at) AS first_file_created,
    max(created_at) AS last_file_created,
    count(*) FILTER (WHERE created_at > now() + interval '1 day') AS future_created,
    count(*) FILTER (WHERE updated_at > now() + interval '1 day') AS future_updated
FROM public.files;
