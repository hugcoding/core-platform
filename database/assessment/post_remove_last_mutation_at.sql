\pset pager off

SELECT table_name, column_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'files'
  AND column_name = 'last_mutation_at';

SELECT
    count(*) AS files_total,
    count(*) FILTER (WHERE last_mutation_type <> 'UNKNOWN') AS classified_mutations,
    count(*) FILTER (WHERE updated_at IS NULL) AS missing_updated_at
FROM public.files;

SELECT last_mutation_type, count(*)
FROM public.files
GROUP BY last_mutation_type
ORDER BY count(*) DESC;
