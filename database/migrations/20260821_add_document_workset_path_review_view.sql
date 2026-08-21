-- Read-only lifecycle and target-path review projection for current workset documents.
BEGIN;

CREATE OR REPLACE VIEW public.v_document_workset_path_review AS
WITH latest_lifecycle AS (
    SELECT DISTINCT ON (file_id)
        file_id, corrected_lifecycle, lifecycle_active_until,
        reviewer, created_at AS lifecycle_reviewed_at
    FROM public.document_review_events
    WHERE review_type = 'lifecycle'
    ORDER BY file_id, created_at DESC, id DESC
), latest_target AS (
    SELECT DISTINCT ON (file_id)
        file_id, decision AS target_path_decision,
        proposal_target_path AS core_proposed_path,
        proposed_target_path AS human_proposed_path,
        corrected_category_code, corrected_document_family_code,
        reviewer AS target_path_reviewer, created_at AS target_path_reviewed_at
    FROM public.document_review_events
    WHERE review_type = 'target_path'
    ORDER BY file_id, created_at DESC, id DESC
), latest_classification_proposal AS (
    SELECT DISTINCT ON (p.file_id)
        p.file_id, p.suggested_path, p.created_at AS classification_proposed_at
    FROM public.classification_proposals p
    JOIN public.files f
      ON f.id = p.file_id
     AND f.deleted_at IS NULL
     AND f.content_sha256 = p.content_sha256
    ORDER BY p.file_id, p.created_at DESC, p.id DESC
), resolved AS (
    SELECT
        w.*,
        CASE w.workset_status
            WHEN 'active' THEN 'active'
            WHEN 'inactive' THEN 'archive'
            ELSE 'needs_review'
        END AS calculated_lifecycle,
        CASE
            WHEN l.corrected_lifecycle = 'active'
             AND l.lifecycle_active_until IS NOT NULL
             AND l.lifecycle_active_until <= now()
                THEN CASE w.workset_status
                    WHEN 'active' THEN 'active'
                    WHEN 'inactive' THEN 'archive'
                    ELSE 'needs_review'
                END
            ELSE COALESCE(
                l.corrected_lifecycle,
                CASE w.workset_status
                    WHEN 'active' THEN 'active'
                    WHEN 'inactive' THEN 'archive'
                    ELSE 'needs_review'
                END
            )
        END AS effective_lifecycle,
        l.lifecycle_active_until,
        l.reviewer AS lifecycle_reviewer,
        l.lifecycle_reviewed_at,
        t.target_path_decision,
        t.core_proposed_path,
        t.human_proposed_path,
        t.corrected_category_code,
        t.corrected_document_family_code,
        t.target_path_reviewer,
        t.target_path_reviewed_at,
        COALESCE(
            t.human_proposed_path,
            t.core_proposed_path,
            c.suggested_path,
            p.suggested_path
        ) AS stored_proposed_path,
        c.category AS accepted_category,
        c.document_family AS accepted_document_family,
        c.suggested_path AS accepted_classification_path,
        p.suggested_path AS latest_classification_proposal_path,
        p.classification_proposed_at
    FROM public.v_active_document_workset w
    LEFT JOIN latest_lifecycle l ON l.file_id = w.file_id
    LEFT JOIN latest_target t ON t.file_id = w.file_id
    LEFT JOIN public.v_current_file_classification c ON c.file_id = w.file_id
    LEFT JOIN latest_classification_proposal p ON p.file_id = w.file_id
), aligned AS (
    SELECT
        r.*,
        CASE r.effective_lifecycle
            WHEN 'active' THEN 'active'
            WHEN 'archive' THEN 'inactive'
            ELSE 'needs_review'
        END AS effective_workset_status,
        CASE r.effective_lifecycle
            WHEN 'active' THEN 'Actief'
            WHEN 'archive' THEN 'Inactief'
            ELSE 'Te beoordelen'
        END AS expected_target_zone
    FROM resolved r
)
SELECT
    a.file_id,
    a.content_group_id,
    a.filename,
    a.extension,
    a.path AS source_path,
    a.content_sha256,
    a.calculated_lifecycle,
    a.effective_lifecycle,
    a.effective_workset_status,
    a.lifecycle_active_until,
    a.reason_code AS workset_reason_code,
    a.accepted_category,
    a.accepted_document_family,
    a.corrected_category_code,
    a.corrected_document_family_code,
    a.target_path_decision,
    a.core_proposed_path,
    a.human_proposed_path,
    a.accepted_classification_path,
    a.latest_classification_proposal_path,
    a.stored_proposed_path,
    CASE
        WHEN a.stored_proposed_path IS NULL THEN NULL
        WHEN a.stored_proposed_path ~ '^/volume1/data/Persoonlijk/(Actief|Inactief|Te beoordelen)/'
            THEN regexp_replace(
                a.stored_proposed_path,
                '^/volume1/data/Persoonlijk/(Actief|Inactief|Te beoordelen)/',
                '/volume1/data/Persoonlijk/' || a.expected_target_zone || '/'
            )
        ELSE a.stored_proposed_path
    END AS lifecycle_aligned_proposed_path,
    CASE
        WHEN a.stored_proposed_path IS NULL THEN false
        WHEN a.stored_proposed_path ~ '^/volume1/data/Persoonlijk/(Actief|Inactief|Te beoordelen)/'
            THEN a.stored_proposed_path NOT LIKE
                '/volume1/data/Persoonlijk/' || a.expected_target_zone || '/%'
        ELSE false
    END AS path_requires_lifecycle_correction,
    a.lifecycle_reviewer,
    a.lifecycle_reviewed_at,
    a.target_path_reviewer,
    a.target_path_reviewed_at,
    a.classification_proposed_at
FROM aligned a;

COMMENT ON VIEW public.v_document_workset_path_review IS
    'Read-only current workset lifecycle and stored path proposals, including a lifecycle-aligned path for human review; never mutates files.';

COMMIT;
