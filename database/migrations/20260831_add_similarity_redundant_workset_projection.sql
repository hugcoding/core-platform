-- SCRUM-115: project reviewed content-similar redundants through their leader.
-- This is read-only derivation; reviews, classifications and file rows remain append-only.
BEGIN;

CREATE OR REPLACE VIEW public.v_pdf_similarity_redundant_workset AS
SELECT
    redundant_id.file_id,
    review.id AS similarity_review_event_id,
    review.group_key,
    review.selected_file_id AS leader_file_id,
    leader.filename AS leader_filename,
    leader.path AS leader_registered_path,
    COALESCE(NULLIF(leader_review.corrected_category_code, ''), leader_class.category)
        AS inherited_category,
    COALESCE(NULLIF(leader_review.corrected_document_family_code, ''), leader_class.document_family)
        AS inherited_document_family,
    COALESCE(leader_review.proposed_target_path, leader_review.proposal_target_path,
             leader_class.suggested_path) AS inherited_target_path,
    CASE
      WHEN leader_review.id IS NOT NULL THEN 'leader_human_review'
      WHEN leader_class.file_id IS NOT NULL THEN 'leader_classification'
      ELSE 'leader_unclassified'
    END AS inheritance_source,
    execution.current_status AS execution_item_status,
    execution.batch_status AS execution_batch_status,
    execution.batch_id AS execution_batch_id,
    CASE
      WHEN redundant.deleted_at IS NOT NULL
        OR execution.current_status IN ('verified', 'completed', 'event_correlated')
        THEN 'quarantined'
      WHEN execution.batch_status IN ('approved', 'queued', 'started', 'paused', 'rollback_pending')
        THEN 'pending_execution'
      ELSE 'awaiting_approval'
    END AS quarantine_phase
FROM public.v_latest_pdf_content_similarity_review review
CROSS JOIN LATERAL unnest(review.redundant_file_ids) redundant_id(file_id)
JOIN public.files redundant ON redundant.id = redundant_id.file_id
JOIN public.files leader ON leader.id = review.selected_file_id
LEFT JOIN public.v_current_file_classification leader_class
  ON leader_class.file_id = leader.id
LEFT JOIN public.v_latest_document_review leader_review
  ON leader_review.file_id = leader.id
 AND leader_review.review_type = 'target_path'
 AND leader_review.decision = 'accepted'
LEFT JOIN LATERAL (
    SELECT status.current_status, status.batch_id, progress.batch_status
    FROM public.v_controlled_execution_item_status status
    LEFT JOIN public.v_controlled_execution_batch_progress progress
      ON progress.id = status.batch_id
    WHERE status.file_id = redundant.id
      AND status.action_type = 'quarantine_content_similar'
      AND status.evidence_snapshot->>'review_event_id' = review.id::text
    ORDER BY status.status_changed_at DESC, status.id DESC
    LIMIT 1
) execution ON true
WHERE review.action = 'selected_leader';

COMMENT ON VIEW public.v_pdf_similarity_redundant_workset IS
  'Reviewed PDF redundants linked to their selected leader, inherited taxonomy and controlled quarantine phase.';

COMMIT;
