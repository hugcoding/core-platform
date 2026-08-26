-- Resolve the current CORE-managed physical path without rewriting files.path.
BEGIN;

CREATE OR REPLACE VIEW public.v_workset_current_physical_location AS
SELECT DISTINCT ON (status.file_id)
       status.file_id,
       status.plan_id,
       status.id AS plan_item_id,
       status.source_path AS registered_source_path,
       status.target_path AS current_path,
       status.effective_lifecycle,
       status.deletion_nomination_id,
       status.current_status,
       status.status_changed_at,
       CASE
           WHEN status.effective_lifecycle = 'deletion_review' THEN 'deletion_quarantine'
           WHEN status.effective_lifecycle = 'archive' THEN 'personal_inactive'
           ELSE 'personal_active'
       END AS location_kind
FROM public.v_personal_migration_item_status status
WHERE status.current_status IN ('verified', 'event_correlated')
ORDER BY status.file_id, status.status_changed_at DESC, status.id DESC;

COMMENT ON VIEW public.v_workset_current_physical_location IS
    'Current verified CORE-managed physical path for Workset display and read-only access; files.path remains immutable audit evidence.';

COMMIT;
