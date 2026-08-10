-- Restore the pre-resolution temporal profile while preserving all evidence.
BEGIN;

CREATE OR REPLACE VIEW public.v_file_temporal_profile AS
WITH current_evidence AS (
    SELECT f.id AS profile_file_id, e.*,
           CASE e.confidence WHEN 'high' THEN 3 WHEN 'medium' THEN 2 ELSE 1 END AS confidence_rank,
           CASE e.source_type
               WHEN 'office_core_properties' THEN 3
               WHEN 'pdf_xmp' THEN 3
               WHEN 'pdf_info_dictionary' THEN 2
               ELSE 1
           END AS source_rank
    FROM public.file_date_evidence e
    JOIN public.files f ON (
        (e.evidence_scope = 'content' AND f.content_sha256 = e.content_sha256)
        OR (e.evidence_scope = 'file' AND f.id = e.file_id)
    )
    WHERE f.deleted_at IS NULL
      AND (e.evidence_scope = 'content' OR f.content_sha256 = e.content_sha256)
), ranked AS (
    SELECT e.*,
           row_number() OVER (
               PARTITION BY e.profile_file_id, e.date_type
               ORDER BY (e.value_at IS NOT NULL) DESC, e.confidence_rank DESC,
                        e.source_rank DESC, e.observed_at DESC, e.id DESC
           ) AS position
    FROM current_evidence e
), aggregate_evidence AS (
    SELECT profile_file_id,
           count(*) AS evidence_count,
           count(DISTINCT COALESCE(value_at::text, local_value::text))
               FILTER (WHERE date_type = 'created') > 1 AS created_has_conflict,
           count(DISTINCT COALESCE(value_at::text, local_value::text))
               FILTER (WHERE date_type = 'modified') > 1 AS modified_has_conflict
    FROM current_evidence
    GROUP BY profile_file_id
)
SELECT f.id AS file_id,
       created.value_at AS source_created_at,
       created.local_value AS source_created_local_value,
       created.confidence AS created_confidence,
       created.source_type AS created_source_type,
       created.id AS created_evidence_id,
       modified.value_at AS source_modified_at,
       modified.local_value AS source_modified_local_value,
       modified.confidence AS modified_confidence,
       modified.source_type AS modified_source_type,
       modified.id AS modified_evidence_id,
       COALESCE(a.evidence_count, 0) AS evidence_count,
       COALESCE(a.created_has_conflict, false) AS created_has_conflict,
       COALESCE(a.modified_has_conflict, false) AS modified_has_conflict
FROM public.files f
LEFT JOIN ranked created
    ON created.profile_file_id = f.id AND created.date_type = 'created' AND created.position = 1
LEFT JOIN ranked modified
    ON modified.profile_file_id = f.id AND modified.date_type = 'modified' AND modified.position = 1
LEFT JOIN aggregate_evidence a ON a.profile_file_id = f.id
WHERE f.deleted_at IS NULL;

DROP VIEW IF EXISTS public.v_file_temporal_resolution;

COMMENT ON VIEW public.v_file_temporal_profile IS
    'Best current created/modified interpretation per active file, restricted to its current content hash.';

COMMIT;
