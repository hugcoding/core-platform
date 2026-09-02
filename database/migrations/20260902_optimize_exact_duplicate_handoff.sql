-- Compute the group evidence once per statement, not once per duplicate.
-- MATERIALIZED is a statement-local result, not a stale persistent cache.
BEGIN;
CREATE OR REPLACE VIEW public.v_exact_duplicate_review_handoff AS
WITH groups_snapshot AS MATERIALIZED (
    SELECT * FROM public.v_exact_duplicate_review_groups
)
SELECT
    review.id AS review_event_id,
    review.content_group_id,
    review.content_sha256,
    review.selected_file_id,
    redundant.file_id AS redundant_file_id,
    selected.path AS selected_path,
    duplicate.path AS redundant_path,
    review.quarantine_root || '/' || review.content_group_id::text || '/'
        || duplicate.id::text || '-' || duplicate.filename AS quarantine_path,
    'inactive'::text AS intended_lifecycle,
    'redundant_duplicate'::text AS nomination_reason,
    review.policy_id,
    review.policy_code,
    review.policy_version,
    (groups.golden_file_id = review.selected_file_id) AS selected_is_current_golden,
    (
        review.action = 'selected_leader'
        AND groups.evidence_current
        AND groups.golden_file_id = review.selected_file_id
        AND selected.deleted_at IS NULL
        AND duplicate.deleted_at IS NULL
        AND selected.content_sha256 = review.content_sha256
        AND duplicate.content_sha256 = review.content_sha256
        AND selected.size_bytes = review.size_bytes
        AND duplicate.size_bytes = review.size_bytes
    ) AS eligible_for_executor,
    CASE
        WHEN review.action <> 'selected_leader' THEN 'review_withdrawn'
        WHEN NOT groups.evidence_current THEN 'duplicate_evidence_changed'
        WHEN groups.golden_file_id <> review.selected_file_id THEN 'golden_switch_required'
        WHEN selected.deleted_at IS NOT NULL OR duplicate.deleted_at IS NOT NULL THEN 'copy_unavailable'
        WHEN selected.content_sha256 <> review.content_sha256
          OR duplicate.content_sha256 <> review.content_sha256
          OR selected.size_bytes <> review.size_bytes
          OR duplicate.size_bytes <> review.size_bytes THEN 'duplicate_changed_after_nomination'
        ELSE 'ready_for_controlled_handoff'
    END AS handoff_reason
FROM public.v_latest_exact_duplicate_review review
JOIN groups_snapshot groups USING (content_group_id)
JOIN public.files selected ON selected.id = review.selected_file_id
CROSS JOIN LATERAL unnest(review.redundant_file_ids) redundant(file_id)
JOIN public.files duplicate ON duplicate.id = redundant.file_id;
COMMIT;
