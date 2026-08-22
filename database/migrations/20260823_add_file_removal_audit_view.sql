-- Explain effective file removals without rewriting the append-only source events.
BEGIN;

CREATE OR REPLACE VIEW public.v_file_removal_audit AS
SELECT
    file_event.id AS file_event_id,
    file_event.file_id,
    file_event.old_path AS removed_path,
    file_event.created_at AS observed_at,
    file_event.source AS observed_by,
    CASE
        WHEN duplicate_correlation.id IS NOT NULL THEN 'core_quarantine'
        WHEN migration_correlation.id IS NOT NULL THEN 'core_migration'
        ELSE 'external_or_unattributed'
    END AS removal_origin,
    CASE
        WHEN duplicate_correlation.id IS NOT NULL
            OR migration_correlation.id IS NOT NULL THEN 'core_managed'
        ELSE 'unattributed'
    END AS initiator_kind,
    COALESCE(duplicate_correlation.actor, migration_correlation.actor) AS operation_actor,
    COALESCE(duplicate_correlation.created_at, migration_correlation.created_at)
        AS operation_correlated_at,
    COALESCE(duplicate_item.plan_id, migration_item.plan_id) AS operation_plan_id,
    COALESCE(duplicate_item.id, migration_item.id) AS operation_item_id,
    COALESCE(duplicate_item.quarantine_path, migration_item.target_path) AS operation_target_path,
    COALESCE(
        duplicate_verified.details->>'content_sha256',
        migration_verified.details->>'content_sha256'
    ) AS verified_sha256,
    CASE
        WHEN duplicate_correlation.id IS NOT NULL
            THEN COALESCE((duplicate_verified.details->>'recovery_available')::boolean, false)
        WHEN migration_correlation.id IS NOT NULL THEN true
        ELSE NULL
    END AS recovery_available,
    CASE
        WHEN duplicate_correlation.id IS NOT NULL
            THEN COALESCE((duplicate_verified.details->>'physical_purge')::boolean, false)
        ELSE false
    END AS physical_purge,
    COALESCE(
        (duplicate_correlation.details->>'qualifies_for_activation')::boolean,
        (migration_correlation.details->>'qualifies_for_activation')::boolean,
        false
    ) AS qualifies_for_activation,
    CASE
        WHEN duplicate_correlation.id IS NOT NULL
            OR migration_correlation.id IS NOT NULL THEN 'correlated'
        ELSE 'observed_only'
    END AS audit_status
FROM public.v_file_events_effective file_event
LEFT JOIN LATERAL (
    SELECT event.*
    FROM public.duplicate_cleanup_events event
    WHERE event.event_type = 'event_correlated'
      AND event.details->>'file_event_id' = file_event.id::text
    ORDER BY event.created_at DESC, event.id DESC
    LIMIT 1
) duplicate_correlation ON true
LEFT JOIN public.duplicate_cleanup_plan_items duplicate_item
    ON duplicate_item.id = duplicate_correlation.item_id
LEFT JOIN LATERAL (
    SELECT event.*
    FROM public.duplicate_cleanup_events event
    WHERE event.item_id = duplicate_item.id
      AND event.event_type = 'verified'
    ORDER BY event.created_at DESC, event.id DESC
    LIMIT 1
) duplicate_verified ON true
LEFT JOIN LATERAL (
    SELECT event.*
    FROM public.personal_migration_events event
    WHERE event.event_type = 'event_correlated'
      AND event.details->>'file_event_id' = file_event.id::text
    ORDER BY event.created_at DESC, event.id DESC
    LIMIT 1
) migration_correlation ON true
LEFT JOIN public.personal_migration_plan_items migration_item
    ON migration_item.id = migration_correlation.item_id
LEFT JOIN LATERAL (
    SELECT event.*
    FROM public.personal_migration_events event
    WHERE event.item_id = migration_item.id
      AND event.event_type = 'verified'
    ORDER BY event.created_at DESC, event.id DESC
    LIMIT 1
) migration_verified ON true
WHERE file_event.event_type = 'DELETED';

COMMENT ON VIEW public.v_file_removal_audit IS
    'Read-only attribution of effective removals to verified CORE operations; unmatched events remain external_or_unattributed and are never assumed manual.';

COMMIT;
