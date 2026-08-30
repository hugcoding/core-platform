BEGIN;
DROP VIEW IF EXISTS public.v_pdf_content_similarity_quarantine_handoff;
DROP VIEW IF EXISTS public.v_pdf_content_similarity_groups;

CREATE VIEW public.v_pdf_content_similarity_groups AS
WITH current_evidence AS (
    SELECT e.*, f.filename, f.path, f.size_bytes, f.deleted_at
    FROM public.v_latest_pdf_content_similarity_evidence e
    JOIN public.files f ON f.id = e.file_id
    WHERE f.deleted_at IS NULL AND f.content_sha256 = e.content_sha256
      AND NOT e.signature_present AND jsonb_array_length(e.extraction_warnings) = 0
), grouped AS (
    SELECT normalized_text_sha256 AS group_key,
           min(page_count) AS page_count, min(normalized_text_characters) AS normalized_text_characters,
           count(*) AS available_documents, count(DISTINCT content_sha256) AS distinct_binary_hashes,
           array_agg(file_id ORDER BY lower(path), file_id) AS file_ids,
           array_agg(id ORDER BY lower(path), file_id) AS evidence_ids
    FROM current_evidence GROUP BY normalized_text_sha256
    HAVING count(*) > 1 AND count(DISTINCT content_sha256) > 1
       AND count(DISTINCT page_text_sha256) = 1
)
SELECT g.*, r.id AS latest_review_id, r.action AS latest_review_action,
       r.selected_file_id, r.redundant_file_ids,
       r.review_notes, r.reviewer, r.created_at AS reviewed_at
FROM grouped g
LEFT JOIN public.v_latest_pdf_content_similarity_review r
  ON r.group_key = g.group_key AND r.file_ids = g.file_ids AND r.evidence_ids = g.evidence_ids;

CREATE VIEW public.v_pdf_content_similarity_quarantine_handoff AS
SELECT r.id AS review_event_id, r.group_key, r.selected_file_id,
       duplicate.file_id AS redundant_file_id,
       leader.path AS leader_path, redundant.path AS redundant_path,
       redundant.content_sha256 AS redundant_content_sha256,
       redundant.size_bytes AS redundant_size_bytes,
       '/volume1/data/.core/quarantaine/duplicaten/inhoudelijk/' || r.group_key || '/'
         || redundant.id::text || '-' || redundant.filename AS quarantine_path,
       (r.action = 'selected_leader'
         AND leader.deleted_at IS NULL AND redundant.deleted_at IS NULL
         AND leader.content_sha256 = leader_evidence.content_sha256
         AND redundant.content_sha256 = redundant_evidence.content_sha256
         AND leader_evidence.normalized_text_sha256 = r.group_key
         AND redundant_evidence.normalized_text_sha256 = r.group_key
         AND leader_evidence.page_text_sha256 = redundant_evidence.page_text_sha256
       ) AS eligible_for_cleanup,
       'human_selected_content_similar_duplicate'::text AS nomination_reason
FROM public.v_latest_pdf_content_similarity_review r
JOIN public.files leader ON leader.id = r.selected_file_id
JOIN public.v_latest_pdf_content_similarity_evidence leader_evidence ON leader_evidence.file_id = leader.id
CROSS JOIN LATERAL unnest(r.redundant_file_ids) duplicate(file_id)
JOIN public.files redundant ON redundant.id = duplicate.file_id
JOIN public.v_latest_pdf_content_similarity_evidence redundant_evidence ON redundant_evidence.file_id = redundant.id
WHERE r.action = 'selected_leader';
COMMIT;
