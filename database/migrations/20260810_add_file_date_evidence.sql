-- SCRUM-69: generic, append-only temporal evidence for documents and future media.
BEGIN;

CREATE TABLE IF NOT EXISTS public.file_date_evidence (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id bigint REFERENCES public.files(id) ON DELETE SET NULL,
    content_group_id uuid REFERENCES public.content_groups(id) ON DELETE SET NULL,
    content_sha256 text NOT NULL,
    evidence_scope text NOT NULL CHECK (evidence_scope IN ('content', 'file')),
    date_type text NOT NULL CHECK (date_type IN (
        'created', 'modified', 'captured', 'digitized', 'encoded', 'published', 'uploaded'
    )),
    source_type text NOT NULL,
    source_field text NOT NULL,
    value_at timestamptz,
    local_value timestamp without time zone NOT NULL,
    timezone_offset_minutes integer CHECK (
        timezone_offset_minutes IS NULL OR timezone_offset_minutes BETWEEN -840 AND 840
    ),
    timezone_status text NOT NULL CHECK (
        timezone_status IN ('utc', 'explicit_offset', 'absent')
    ),
    raw_value text NOT NULL,
    confidence text NOT NULL CHECK (confidence IN ('low', 'medium', 'high')),
    extractor_version text NOT NULL,
    idempotency_key text NOT NULL UNIQUE,
    observed_at timestamptz NOT NULL DEFAULT now(),
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (value_at IS NOT NULL OR timezone_status = 'absent'),
    CHECK (evidence_scope <> 'file' OR file_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_file_date_evidence_file_type
    ON public.file_date_evidence(file_id, date_type, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_file_date_evidence_content
    ON public.file_date_evidence(content_sha256, evidence_scope, date_type);
CREATE INDEX IF NOT EXISTS idx_file_date_evidence_group
    ON public.file_date_evidence(content_group_id, date_type)
    WHERE content_group_id IS NOT NULL;

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

COMMENT ON TABLE public.file_date_evidence IS
    'Append-only source observations for temporal metadata; conflicting evidence is retained.';
COMMENT ON VIEW public.v_file_temporal_profile IS
    'Best current created/modified interpretation per active file, restricted to its current content hash.';

COMMIT;
