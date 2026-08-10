-- SCRUM-89: database-backed, read-only active document workset projection.
BEGIN;

CREATE OR REPLACE VIEW public.v_active_document_workset AS
WITH selected_policy AS (
    SELECT
        p.id AS policy_id,
        p.policy_version,
        p.contract_version,
        p.configuration_checksum,
        p.effective_from,
        p.configuration,
        (p.configuration ->> 'activity_window_months')::integer AS activity_window_months
    FROM public.v_current_policies p
    WHERE p.policy_code = 'active_document_workset'
      AND p.environment = COALESCE(
          NULLIF(current_setting('core.environment', true), ''),
          'acceptance'
      )
      AND p.configuration ->> 'activity_window_months' ~ '^[0-9]+$'
      AND (p.configuration ->> 'activity_window_months')::integer BETWEEN 1 AND 24
      AND jsonb_typeof(p.configuration -> 'extensions') = 'array'
      AND jsonb_typeof(p.configuration -> 'source_roots') = 'array'
      AND p.configuration ->> 'golden_records_only' = 'true'
    ORDER BY p.effective_from DESC, p.id DESC
    LIMIT 1
), scoped_golden_records AS (
    SELECT
        p.*,
        cg.id AS content_group_id,
        cg.confidence AS golden_confidence,
        cg.algorithm_version AS golden_algorithm_version,
        f.id AS file_id,
        f.path,
        f.filename,
        lower(coalesce(f.extension, '')) AS extension,
        f.mime_type,
        f.size_bytes,
        f.content_sha256,
        f.modified_at_fs,
        CASE
            WHEN f.modified_at_fs BETWEEN 1 AND 32503680000
                THEN to_timestamp(f.modified_at_fs)
        END AS filesystem_modified_at,
        tp.source_created_at,
        tp.created_confidence,
        tp.created_source_type,
        tp.source_modified_at,
        tp.modified_confidence,
        tp.modified_source_type,
        tp.evidence_count AS temporal_evidence_count,
        tp.created_has_conflict,
        tp.modified_has_conflict
    FROM selected_policy p
    JOIN public.content_groups cg ON true
    JOIN public.files f
      ON f.id = cg.golden_file_id
     AND f.deleted_at IS NULL
     AND f.size_bytes > 0
     AND f.content_sha256 IS NOT NULL
    LEFT JOIN public.v_file_temporal_profile tp ON tp.file_id = f.id
    WHERE EXISTS (
        SELECT 1
        FROM jsonb_array_elements_text(p.configuration -> 'extensions') extension(value)
        WHERE lower(extension.value) = lower(coalesce(f.extension, ''))
    )
      AND EXISTS (
        SELECT 1
        FROM jsonb_array_elements_text(p.configuration -> 'source_roots') root(value)
        WHERE f.path = rtrim(root.value, '/')
           OR f.path LIKE rtrim(root.value, '/') || '/%'
    )
), assessed AS (
    SELECT
        d.*,
        activity.activity_at,
        activity.activity_source,
        activity.activity_confidence,
        now() - make_interval(months => d.activity_window_months) AS activity_cutoff_at
    FROM scoped_golden_records d
    LEFT JOIN LATERAL (
        SELECT signal.activity_at, signal.activity_source, signal.activity_confidence
        FROM (VALUES
            (d.source_modified_at, 'source_metadata_modified'::text, d.modified_confidence),
            (d.source_created_at, 'source_metadata_created'::text, d.created_confidence),
            (d.filesystem_modified_at, 'filesystem_mtime'::text, 'low'::text)
        ) AS signal(activity_at, activity_source, activity_confidence)
        WHERE signal.activity_at IS NOT NULL
        ORDER BY signal.activity_at DESC,
                 CASE signal.activity_source
                     WHEN 'source_metadata_modified' THEN 1
                     WHEN 'source_metadata_created' THEN 2
                     ELSE 3
                 END
        LIMIT 1
    ) activity ON true
)
SELECT
    file_id,
    content_group_id,
    path,
    filename,
    extension,
    mime_type,
    size_bytes,
    content_sha256,
    source_created_at,
    source_modified_at,
    filesystem_modified_at,
    activity_at AS last_qualifying_activity_at,
    activity_source AS activity_basis_source,
    COALESCE(activity_confidence, 'low') AS activity_confidence,
    activity_cutoff_at,
    CASE
        WHEN created_has_conflict OR modified_has_conflict THEN 'needs_review'
        WHEN activity_at IS NULL OR activity_at > now() THEN 'needs_review'
        WHEN activity_at >= activity_cutoff_at THEN 'active'
        ELSE 'inactive'
    END AS workset_status,
    CASE
        WHEN created_has_conflict OR modified_has_conflict
            THEN 'conflicting_temporal_evidence'
        WHEN activity_at IS NULL OR activity_at > now()
            THEN 'invalid_or_missing_activity_timestamp'
        WHEN activity_at >= activity_cutoff_at
            THEN activity_source || '_within_configured_window'
        ELSE 'no_qualifying_activity_within_configured_window'
    END AS reason_code,
    COALESCE(created_has_conflict, false) AS created_has_conflict,
    COALESCE(modified_has_conflict, false) AS modified_has_conflict,
    COALESCE(temporal_evidence_count, 0) AS temporal_evidence_count,
    golden_confidence,
    golden_algorithm_version,
    policy_id,
    policy_version,
    contract_version AS policy_contract_version,
    configuration_checksum AS policy_checksum,
    effective_from AS policy_effective_from,
    activity_window_months
FROM assessed;

COMMENT ON VIEW public.v_active_document_workset IS
    'Read-only policy-backed status projection for current personal-document golden records; no file or database mutations.';

COMMIT;
