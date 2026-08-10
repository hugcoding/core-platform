-- SCRUM-89: normalize equivalent PDF timestamps without mutating evidence.
BEGIN;

CREATE OR REPLACE VIEW public.v_file_temporal_resolution AS
WITH current_evidence AS (
    SELECT f.id AS profile_file_id, e.*
    FROM public.file_date_evidence e
    JOIN public.files f ON (
        (e.evidence_scope = 'content' AND f.content_sha256 = e.content_sha256)
        OR (e.evidence_scope = 'file' AND f.id = e.file_id)
    )
    WHERE f.deleted_at IS NULL
      AND (e.evidence_scope = 'content' OR f.content_sha256 = e.content_sha256)
), source_ranked AS (
    SELECT e.*,
           row_number() OVER (
               PARTITION BY e.profile_file_id, e.date_type, e.source_type
               ORDER BY e.observed_at DESC, e.id DESC
           ) AS source_position
    FROM current_evidence e
), inputs AS (
    SELECT e.profile_file_id, e.date_type,
           count(*) AS evidence_count,
           array_agg(e.id ORDER BY e.id) AS evidence_ids,
           count(DISTINCT COALESCE(e.value_at::text, e.local_value::text)) > 1
               AS raw_representation_conflict,
           bool_and(e.source_type IN ('pdf_info_dictionary', 'pdf_xmp'))
               AS pdf_sources_only,
           bool_or(e.source_type = 'pdf_info_dictionary') AS has_pdf_info,
           bool_or(e.source_type = 'pdf_xmp') AS has_pdf_xmp,
           max(e.value_at) FILTER (
               WHERE e.source_type = 'pdf_info_dictionary' AND e.source_position = 1
           ) AS pdf_info_value_at,
           max(e.timezone_status) FILTER (
               WHERE e.source_type = 'pdf_info_dictionary' AND e.source_position = 1
           ) AS pdf_info_timezone_status,
           max(e.local_value) FILTER (
               WHERE e.source_type = 'pdf_xmp' AND e.source_position = 1
           ) AS pdf_xmp_local_value
    FROM source_ranked e
    GROUP BY e.profile_file_id, e.date_type
), classified AS (
    SELECT i.*,
           CASE
               WHEN NOT i.raw_representation_conflict THEN 'consistent'
               WHEN i.pdf_sources_only AND i.has_pdf_info AND i.has_pdf_xmp
                AND i.pdf_info_value_at IS NOT NULL
                AND i.pdf_info_timezone_status IN ('utc', 'explicit_offset')
                AND i.pdf_xmp_local_value IS NOT NULL
                AND abs(extract(epoch FROM (
                    (i.pdf_info_value_at AT TIME ZONE 'UTC') - i.pdf_xmp_local_value
                ))) <= 2
                   THEN 'equivalent'
               WHEN i.pdf_sources_only AND i.has_pdf_info AND i.has_pdf_xmp
                AND i.pdf_info_value_at IS NOT NULL
                AND i.pdf_info_timezone_status IN ('utc', 'explicit_offset')
                AND i.pdf_xmp_local_value IS NOT NULL
                AND i.pdf_xmp_local_value::time = time '00:00:00'
                AND i.pdf_xmp_local_value::date
                    = (i.pdf_info_value_at AT TIME ZONE 'UTC')::date
                   THEN 'equivalent'
               ELSE 'material_conflict'
           END AS resolution_status
    FROM inputs i
)
SELECT profile_file_id AS file_id,
       date_type,
       resolution_status,
       CASE
           WHEN NOT raw_representation_conflict THEN 'consistent_single_value'
           WHEN resolution_status = 'equivalent'
            AND abs(extract(epoch FROM (
                (pdf_info_value_at AT TIME ZONE 'UTC') - pdf_xmp_local_value
            ))) <= 2
               THEN 'pdf_info_xmp_equivalent_instant'
           WHEN resolution_status = 'equivalent'
               THEN 'pdf_info_xmp_equivalent_date_precision'
           ELSE 'materially_different_temporal_evidence'
       END AS resolution_reason,
       'temporal-resolution-v1'::text AS resolution_rule_version,
       (resolution_status = 'material_conflict') AS material_conflict,
       raw_representation_conflict,
       evidence_count,
       evidence_ids,
       pdf_info_value_at,
       pdf_info_timezone_status,
       pdf_xmp_local_value
FROM classified;

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
    SELECT profile_file_id, count(*) AS evidence_count
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
       COALESCE(created_resolution.material_conflict, false) AS created_has_conflict,
       COALESCE(modified_resolution.material_conflict, false) AS modified_has_conflict
FROM public.files f
LEFT JOIN ranked created
    ON created.profile_file_id = f.id AND created.date_type = 'created' AND created.position = 1
LEFT JOIN ranked modified
    ON modified.profile_file_id = f.id AND modified.date_type = 'modified' AND modified.position = 1
LEFT JOIN aggregate_evidence a ON a.profile_file_id = f.id
LEFT JOIN public.v_file_temporal_resolution created_resolution
    ON created_resolution.file_id = f.id AND created_resolution.date_type = 'created'
LEFT JOIN public.v_file_temporal_resolution modified_resolution
    ON modified_resolution.file_id = f.id AND modified_resolution.date_type = 'modified'
WHERE f.deleted_at IS NULL;

COMMENT ON VIEW public.v_file_temporal_resolution IS
    'Audit-friendly temporal-resolution-v1 classification; source evidence remains append-only.';
COMMENT ON VIEW public.v_file_temporal_profile IS
    'Best current created/modified interpretation; conflict flags mean unresolved material conflicts.';

COMMIT;
