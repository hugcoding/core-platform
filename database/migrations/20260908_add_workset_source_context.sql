-- SCRUM-145: recover stable source context without changing current file location.
BEGIN;
SET LOCAL lock_timeout = '2s';

CREATE OR REPLACE VIEW public.v_workset_source_context AS
WITH event_paths AS (
    SELECT
        event.file_id,
        event.id AS source_event_id,
        event.created_at AS source_observed_at,
        candidate.path AS source_context_path,
        candidate.path_kind
    FROM public.v_file_events_effective event
    CROSS JOIN LATERAL (VALUES
        (event.old_path, 'old_path'::text),
        (event.new_path, 'new_path'::text)
    ) candidate(path, path_kind)
    WHERE event.file_id IS NOT NULL
      AND candidate.path IS NOT NULL
      AND lower(candidate.path) LIKE '/volume1/data/import/cloud/onedrive/current/%'
), ranked AS (
    SELECT
        event_paths.*,
        row_number() OVER (
            PARTITION BY file_id
            ORDER BY
                CASE
                    WHEN lower(source_context_path) LIKE '/volume1/data/import/cloud/onedrive/current/documenten/%' THEN 0
                    ELSE 1
                END,
                source_observed_at,
                source_event_id,
                path_kind
        ) AS position
    FROM event_paths
)
SELECT
    file_id,
    source_context_path,
    CASE
        WHEN lower(source_context_path) LIKE '/volume1/data/import/cloud/onedrive/current/documenten/%'
            THEN substring(source_context_path FROM length('/volume1/data/import/cloud/onedrive/current/Documenten/') + 1)
        ELSE substring(source_context_path FROM length('/volume1/data/import/cloud/onedrive/current/') + 1)
    END AS source_context_relative_path,
    source_event_id,
    source_observed_at,
    path_kind AS source_event_path_kind,
    CASE
        WHEN lower(source_context_path) LIKE '/volume1/data/import/cloud/onedrive/current/documenten/%'
            THEN 'earliest_onedrive_documents_path'
        ELSE 'earliest_onedrive_import_path'
    END AS selection_reason
FROM ranked
WHERE position = 1;

COMMENT ON VIEW public.v_workset_source_context IS
    'Read-only canonical historical OneDrive path per file for classification evidence only; never a physical execution target.';

COMMIT;
