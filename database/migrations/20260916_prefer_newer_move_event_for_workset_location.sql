-- Prefer a newer, correlated filesystem move over an older verified migration plan.
BEGIN;

CREATE OR REPLACE VIEW public.v_workset_current_physical_location AS
SELECT DISTINCT ON (status.file_id)
       status.file_id,
       status.plan_id,
       status.id AS plan_item_id,
       status.source_path AS registered_source_path,
       COALESCE(latest_move.new_path, status.target_path) AS current_path,
       status.effective_lifecycle,
       item.deletion_nomination_id,
       status.current_status,
       GREATEST(status.status_changed_at, latest_move.created_at) AS status_changed_at,
       CASE
           WHEN status.effective_lifecycle = 'deletion_review'
             OR latest_move.new_path LIKE '/volume1/data/.core/quarantaine/verwijderreview/%'
               THEN 'deletion_quarantine'
           WHEN COALESCE(latest_move.new_path, status.target_path) LIKE '/volume1/data/Persoonlijk/Inactief/%'
               THEN 'personal_inactive'
           WHEN COALESCE(latest_move.new_path, status.target_path) LIKE '/volume1/data/Persoonlijk/Actief/%'
               THEN 'personal_active'
           WHEN status.effective_lifecycle = 'archive' THEN 'personal_inactive'
           ELSE 'personal_active'
       END AS location_kind
FROM public.v_personal_migration_item_status status
JOIN public.personal_migration_plan_items item ON item.id = status.id
LEFT JOIN LATERAL (
    SELECT event.new_path, event.created_at
    FROM public.file_events event
    WHERE event.file_id = status.file_id
      AND event.event_type = 'MOVED'
      AND event.created_at > status.status_changed_at
      AND event.new_path LIKE '/volume1/data/%'
    ORDER BY event.created_at DESC, event.id DESC
    LIMIT 1
) latest_move ON true
WHERE status.current_status IN ('verified', 'event_correlated')
ORDER BY status.file_id, status.status_changed_at DESC, status.id DESC;

COMMENT ON VIEW public.v_workset_current_physical_location IS
    'Current verified CORE-managed path; a newer correlated MOVED event supersedes a stale migration-plan target.';

COMMIT;
